"""Prepare full-path bounded beacon descriptor ownership in a new source candidate.

Reserve/reuse two host-tracked CCA/APP slots in the unchanged 1000-byte arena,
refuse exhaustion before payload writes, and propagate construction failure to
the real QDRV publication boundary. No source overwrite, binary or hardware use.
"""
from __future__ import annotations
import argparse
from collections import Counter
import difflib
import hashlib
import json
from pathlib import Path
import shutil
from catalog_hgw_firmware_comments import scan_comments

ROOT = Path(__file__).resolve().parents[1]

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def function(text, signature):
    start = text.index(signature); brace = text.index('{', start); depth = 1; end = brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}'); end += 1
    return start, end, text[start:end]

ALLOCATOR = r'''static struct beacon_shared_ie_t *ieee80211_beacon_alloc_ie(struct ieee80211_beacon_param_t *param)
{
    uintptr_t start, curr;
    struct beacon_shared_ie_t *ie;

    if (!param || param->om_build_error)
        return NULL;
    start = (uintptr_t)param->buf;
    curr = (uintptr_t)param->curr;
    if (param->size != BEACON_PARAM_SIZE || curr < start ||
        curr - start > param->size || (curr & 3) ||
        (curr - start) % sizeof(*ie) ||
        param->size - (curr - start) < sizeof(*ie)) {
        param->om_build_error = -ENOSPC;
        return NULL;
    }
    ie = (struct beacon_shared_ie_t *)curr;
    memset(ie, 0, sizeof(*ie));
    param->curr += sizeof(*ie);
    return ie;
}
'''

HELPERS = r'''
/* Reserved dynamic slots are allocated once per unpublished beacon build.
 * Repeated CCA/APP updates never advance curr or enlarge the MuC wire arena. */
static int om_beacon_descriptor_valid(struct ieee80211_beacon_param_t *param,
        struct beacon_shared_ie_t *ie)
{
    uintptr_t start, curr, address;
    if (!param || !ie || param->size != BEACON_PARAM_SIZE)
        return 0;
    start = (uintptr_t)param->buf;
    curr = (uintptr_t)param->curr;
    address = (uintptr_t)ie;
    return curr >= start && curr - start <= param->size &&
        !(start & 3) && (curr - start) % sizeof(*ie) == 0 &&
        address >= start && address - start <= curr - start &&
        curr - address >= sizeof(*ie) && !(address & 3) &&
        (address - start) % sizeof(*ie) == 0;
}

static int om_beacon_slot_error(struct ieee80211_beacon_param_t *param)
{
    if (param && !param->om_build_error)
        param->om_build_error = -EINVAL;
    return -EINVAL;
}

/* Inspect the entire unpublished chain before rewiring any prefix. */
static int om_beacon_chain_valid(struct ieee80211_beacon_param_t *param)
{
    struct beacon_shared_ie_t *ie, *last = NULL;
    struct beacon_shared_ie_t *seen[BEACON_PARAM_SIZE / sizeof(*ie)];
    unsigned int count = 0, cca_seen = 0, app_seen = 0, i;
    uintptr_t previous = 0;

    if (!param || param->om_build_error)
        return -EINVAL;
    if (!om_beacon_descriptor_valid(param, param->om_cca_ie) ||
        !om_beacon_descriptor_valid(param, param->om_app_ie) ||
        param->om_cca_ie == param->om_app_ie)
        return om_beacon_slot_error(param);
    for (ie = param->head; ie; ie = ie->next) {
        if (count >= BEACON_PARAM_SIZE / sizeof(*ie) ||
            !om_beacon_descriptor_valid(param, ie))
            return om_beacon_slot_error(param);
        for (i = 0; i < count; i++)
            if (seen[i] == ie)
                return om_beacon_slot_error(param);
        if (!ie->size || !ie->lhost_buf ||
            (count && (uintptr_t)ie->lhost_buf < previous) ||
            (uintptr_t)ie->lhost_buf + ie->size < (uintptr_t)ie->lhost_buf ||
            (u32)ie->buf != (u32)plat_kernel_addr_to_dma(NULL, ie->lhost_buf) ||
            ie->next_muc_addr != (ie->next ?
                (u32)plat_kernel_addr_to_dma(NULL, ie->next) : 0))
            return om_beacon_slot_error(param);
        seen[count++] = ie;
        previous = (uintptr_t)ie->lhost_buf + ie->size;
        cca_seen += ie == param->om_cca_ie;
        app_seen += ie == param->om_app_ie;
        last = ie;
    }
    if (last != param->tail ||
        cca_seen != !!param->om_cca_ie->size ||
        app_seen != !!param->om_app_ie->size)
        return om_beacon_slot_error(param);
    return 0;
}

static int om_beacon_allocation_ready(struct ieee80211_beacon_param_t *param)
{
    uintptr_t start, curr;
    if (!param || param->om_build_error)
        return 0;
    if (om_beacon_chain_valid(param))
        return 0;
    start = (uintptr_t)param->buf;
    curr = (uintptr_t)param->curr;
    if (param->size != BEACON_PARAM_SIZE || curr < start ||
        curr - start > param->size || (start & 3) || (curr & 3) ||
        (curr - start) % sizeof(struct beacon_shared_ie_t) ||
        param->size - (curr - start) < sizeof(struct beacon_shared_ie_t)) {
        param->om_build_error = -ENOSPC;
        return 0;
    }
    return 1;
}

static int om_beacon_reserved_update(struct ieee80211_beacon_param_t *param,
        struct beacon_shared_ie_t *ie, uint8_t *frm, uint16_t size)
{
    struct beacon_shared_ie_t *cursor, *previous = NULL;
    unsigned int count = 0;

    if (!param || param->om_build_error)
        return -EINVAL;
    if (!om_beacon_descriptor_valid(param, ie) || !frm || !size ||
        (ie != param->om_cca_ie && ie != param->om_app_ie))
        return om_beacon_slot_error(param);
    if (om_beacon_chain_valid(param))
        return -EINVAL;
    if (ie->size && om_beacon_reserved_remove(param, ie))
        return -EINVAL;
    /* Wire traversal must match frame order, including APP-first/CCA-later. */
    for (cursor = param->head; cursor; previous = cursor, cursor = cursor->next) {
        if (count++ >= BEACON_PARAM_SIZE / sizeof(*cursor) ||
            !om_beacon_descriptor_valid(param, cursor) || !cursor->size)
            return om_beacon_slot_error(param);
        if ((uintptr_t)cursor->lhost_buf > (uintptr_t)frm)
            break;
    }
    ieee80211_beacon_associate_ie(ie, frm, size);
    ie->next = cursor;
    ie->next_muc_addr = cursor ? plat_kernel_addr_to_dma(NULL, cursor) : 0;
    if (previous) {
        previous->next = ie;
        previous->next_muc_addr = plat_kernel_addr_to_dma(NULL, ie);
    } else {
        param->head = ie;
    }
    if (!cursor)
        param->tail = ie;
    return 0;
}

static int om_beacon_reserved_remove(struct ieee80211_beacon_param_t *param,
        struct beacon_shared_ie_t *slot)
{
    struct beacon_shared_ie_t *ie, *previous = NULL;
    unsigned int count = 0;

    if (!param || param->om_build_error)
        return -EINVAL;
    if (!om_beacon_descriptor_valid(param, slot) ||
        (slot != param->om_cca_ie && slot != param->om_app_ie))
        return om_beacon_slot_error(param);
    if (om_beacon_chain_valid(param))
        return -EINVAL;
    if (!slot->size)
        return 0;
    for (ie = param->head; ie;
         previous = ie, ie = ie->next) {
        if (count++ >= BEACON_PARAM_SIZE / sizeof(*ie) ||
            !om_beacon_descriptor_valid(param, ie) || !ie->size)
            return om_beacon_slot_error(param);
        if (ie != slot)
            continue;
        if (previous) {
            previous->next = ie->next;
            previous->next_muc_addr = ie->next_muc_addr;
        } else {
            param->head = ie->next;
        }
        if (param->tail == ie)
            param->tail = previous;
        memset(slot, 0, sizeof(*slot));
        return 0;
    }
    return om_beacon_slot_error(param);
}

/* This query is used by QDRV before its hostlink publication. */
int om_ieee80211_beacon_build_status(struct ieee80211_beacon_param_t *param)
{
    if (!param)
        return -EINVAL;
    if (param->om_build_error)
        return param->om_build_error;
    return om_beacon_chain_valid(param);
}
EXPORT_SYMBOL(om_ieee80211_beacon_build_status);

/* Frame extents are checked at complete-state boundaries, before payload writes
 * and again before QDRV publication. Temporary relocation gaps are unpublished. */
int om_ieee80211_beacon_frame_status(struct ieee80211_beacon_param_t *param,
        struct sk_buff *skb)
{
    struct beacon_shared_ie_t *ie;
    uintptr_t cursor, end;
    int status = om_ieee80211_beacon_build_status(param);
    if (status)
        return status;
    if (!skb || !skb->data)
        return om_beacon_slot_error(param);
    cursor = (uintptr_t)skb->data;
    end = cursor + skb->len;
    if (end < cursor || !param->head)
        return om_beacon_slot_error(param);
    for (ie = param->head; ie; ie = ie->next) {
        if ((uintptr_t)ie->lhost_buf != cursor || ie->size > end - cursor)
            return om_beacon_slot_error(param);
        cursor += ie->size;
    }
    if (cursor != end)
        return om_beacon_slot_error(param);
    return 0;
}
EXPORT_SYMBOL(om_ieee80211_beacon_frame_status);
'''

CCA_UPDATE = r'''
        /* Change the CCA payload once, then reuse its reserved descriptor.
         * Move a following APP payload before inserting/removing CCA bytes. */
        {
            unsigned int old_len = vap->param->om_cca_ie->size;
            unsigned int old_app_len = vap->param->om_app_ie->size;
            unsigned int new_len = 0;
            int delta;
#if defined(CONFIG_QTN_80211K_SUPPORT)
            if (ic->ic_flags & IEEE80211_F_CCA)
                new_len = sizeof(struct ieee80211_ie_measreq) +
                    sizeof(struct ieee80211_ie_measure_comm);
#else
            if (ic->ic_flags & IEEE80211_F_CCA)
                new_len = sizeof(struct ieee80211_ie_measreq);
#endif
            delta = (int)new_len - (int)old_len;
            if (delta > 0 && skb_tailroom(skb) < delta) {
                vap->param->om_build_error = -ENOSPC;
                goto om_beacon_update_end;
            }
            if (delta) {
                /* Detach both old extents before their payload positions move. */
                if (om_beacon_reserved_remove(vap->param, vap->param->om_cca_ie) ||
                    om_beacon_reserved_remove(vap->param, vap->param->om_app_ie))
                    goto om_beacon_update_end;
                memmove(bo->bo_appie_buf + delta, bo->bo_appie_buf,
                    bo->bo_appie_buf_len);
                bo->bo_xr += delta;
                bo->bo_appie_buf += delta;
                bo->bo_tim_trailerlen += delta;
                if (delta > 0)
                    skb_put(skb, delta);
                else
                    skb_trim(skb, skb->len + delta);
                if (old_app_len &&
                    om_beacon_reserved_update(vap->param,
                        vap->param->om_app_ie, bo->bo_appie_buf,
                        bo->bo_appie_buf_len))
                    goto om_beacon_update_end;
            }
            if (new_len)
                (void)ieee80211_add_beacon_desc_ie(ni,
                    IEEE80211_ELEMID_MEASREQ, bo->bo_cca);
            else if (om_beacon_reserved_remove(vap->param,
                    vap->param->om_cca_ie))
                goto om_beacon_update_end;
            if (vap->param->om_build_error)
                goto om_beacon_update_end;
        }
'''

APP_UPDATE = r'''
    /* APP payload replacement uses one reserved slot, including removal. */
    {
        unsigned int new_len = vap->app_ie[IEEE80211_APPIE_FRAME_BEACON].ie ?
            vap->app_ie[IEEE80211_APPIE_FRAME_BEACON].length : 0;
        int delta = (int)new_len - (int)bo->bo_appie_buf_len;

        if (delta > 0 && skb_tailroom(skb) < delta) {
            vap->param->om_build_error = -ENOSPC;
            goto om_beacon_update_end;
        }
        if (delta > 0)
            skb_put(skb, delta);
        else if (delta < 0)
            skb_trim(skb, skb->len + delta);
        bo->bo_appie_buf_len = new_len;
        bo->bo_tim_trailerlen += delta;
        if (new_len)
            (void)ieee80211_add_beacon_desc_ie(ni,
                IEEE80211_ELEMID_VENDOR_APP, bo->bo_appie_buf);
        else if (om_beacon_reserved_remove(vap->param,
                vap->param->om_app_ie))
            goto om_beacon_update_end;
        if (vap->param->om_build_error)
            goto om_beacon_update_end;
        vap->iv_flags_ext &= ~IEEE80211_FEXT_APPIE_UPDATE;
    }
'''

def preserve_replace(text, signature, replacement):
    start, end, old = function(text, signature)
    return text[:start] + replacement + '\n#if 0 /* Preserved original algorithm for source provenance. */\n' + old + '\n#endif\n' + text[end:]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    proof=json.loads((a.parent/'result.json').read_text());assert proof['total_original_entries_added']==19
    assert not a.output.exists();a.output.mkdir(parents=True)
    shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers')
    wlan=a.output/'source/wlan';qdrv=a.output/'source/qdrv';shutil.copytree(ROOT/'outputs/rea/bbdf-recovery-candidate-20261022T144500Z-r1/source/qdrv',qdrv)
    # Match the parent capability branch's QDRV fourteen-entry lineage. Never
    # silently join the separate eighteen-entry RTS/SIFS research branch.
    touched={};base_header=ROOT/'work/sources/Quantenna-GPL/drivers/include/kernel/net80211/ieee80211_beacon_desc.h'
    header=a.output/'headers/net80211/ieee80211_beacon_desc.h';old=base_header.read_text();touched[str(header.relative_to(a.output))]=old
    marker='\tuint16_t size;\t\t\t\t/* allocated buffer size */\n};'
    assert marker in old
    extra='''\n\t/* Host-only ownership metadata after the fixed MuC-compatible prefix. */
\tstruct beacon_shared_ie_t *om_cca_ie;
\tstruct beacon_shared_ie_t *om_app_ie;
\tint om_build_error;
'''
    new=old.replace(marker,marker.replace('\n};',extra+'};'),1)
    new=new.replace('void ieee80211_dump_beacon_desc_ie', 'int om_ieee80211_beacon_build_status(struct ieee80211_beacon_param_t *param);\nvoid ieee80211_dump_beacon_desc_ie',1)
    header.write_text(new,encoding='utf-8',newline='\n')
    desc=wlan/'ieee80211_beacon_desc.c';old=desc.read_text();touched[str(desc.relative_to(a.output))]=old
    new=old.replace('uint8_t *frm, uint8_t size)','uint8_t *frm, uint16_t size)',1)
    new=preserve_replace(new,'static struct beacon_shared_ie_t *ieee80211_beacon_alloc_ie(',ALLOCATOR)
    marker='/*\n * This function allocates an ie descriptor, construct it with ie payload buffer and'
    assert marker in new
    new=new.replace(marker,'static int om_beacon_chain_valid(struct ieee80211_beacon_param_t *param);\n\n'+marker,1)
    for signature in ('static void ieee80211_add_beacon_ie_desc(', 'static void ieee80211_add_beacon_ie_desc_head('):
        start,end,body=function(new,signature)
        body=body.replace('\tnew_ie = ieee80211_beacon_alloc_ie(param);','\tif (om_beacon_chain_valid(param))\n\t\treturn;\n\tnew_ie = ieee80211_beacon_alloc_ie(param);',1)
        new=new[:start]+body+new[end:]
    marker='int ieee80211_beacon_create_param(';new=new.replace(marker,HELPERS+'\n'+marker,1)
    init='\tvap->param->tail = NULL;\n\treturn 0;'
    assert init in new
    new=new.replace(init,'''\tvap->param->tail = NULL;
\tvap->param->om_build_error = 0;
\tvap->param->om_cca_ie = ieee80211_beacon_alloc_ie(vap->param);
\tvap->param->om_app_ie = ieee80211_beacon_alloc_ie(vap->param);
\tif (!vap->param->om_cca_ie || !vap->param->om_app_ie) {
\t\tkfree(vap->param);
\t\tvap->param = NULL;
\t\treturn -ENOSPC;
\t}
\treturn 0;''',1)
    for signature in ('uint8_t *ieee80211_add_beacon_desc_header(', 'uint8_t *ieee80211_add_beacon_desc_mandatory_fields('):
        start,end,body=function(new,signature);needle='\n\tpost_frm = '
        body=body.replace(needle,'\n\t/* Check the exact next slot before touching payload bytes. */\n\tif (!om_beacon_allocation_ready(param))\n\t\treturn frm;\n'+needle,1)
        new=new[:start]+body+new[end:]
    marker='\tif (param == NULL)\n\t\treturn 0;\n\n\tswitch (ext_ie_id) {';assert marker in new
    new=new.replace(marker,'''\tif (param == NULL)
\t\treturn 0;
\tif (param->om_build_error)
\t\treturn pre_frm;
\tif (om_ieee80211_beacon_build_status(param))
\t\treturn pre_frm;
\tif (ext_ie_id != IEEE80211_ELEMID_MEASREQ &&
\t    ext_ie_id != IEEE80211_ELEMID_VENDOR_APP &&
\t    !om_beacon_allocation_ready(param)) {
\t\treturn pre_frm;
\t}

\tswitch (ext_ie_id) {''',1)
    marker='\tif (post_frm != pre_frm)\n\t\tieee80211_add_beacon_ie_desc(param, pre_frm, post_frm - pre_frm);';assert marker in new
    new=new.replace(marker,'''\tif (post_frm != pre_frm) {
\t\tif (ext_ie_id == IEEE80211_ELEMID_MEASREQ)
\t\t\t(void)om_beacon_reserved_update(param, param->om_cca_ie, pre_frm, post_frm - pre_frm);
\t\telse if (ext_ie_id == IEEE80211_ELEMID_VENDOR_APP)
\t\t\t(void)om_beacon_reserved_update(param, param->om_app_ie, pre_frm, post_frm - pre_frm);
\t\telse
\t\t\tieee80211_add_beacon_ie_desc(param, pre_frm, post_frm - pre_frm);
\t}''',1)
    # Helpers are local to this C unit; expose only checked dynamic remove/update
    # wrappers, preserving the MuC descriptor layout and fixed arena size.
    for name in ('om_beacon_reserved_update','om_beacon_reserved_remove'):
        new=new.replace('static int '+name+'(', 'int '+name+'(',1)
        _,end,_=function(new,'int '+name+'(');new=new[:end]+'\nEXPORT_SYMBOL('+name+');'+new[end:]
    header_text=header.read_text();header_text=header_text.replace('int om_ieee80211_beacon_build_status', 'int om_beacon_reserved_update(struct ieee80211_beacon_param_t *param, struct beacon_shared_ie_t *ie, uint8_t *frm, uint16_t size);\nint om_beacon_reserved_remove(struct ieee80211_beacon_param_t *param, struct beacon_shared_ie_t *ie);\nint om_ieee80211_beacon_build_status',1);header.write_text(header_text,encoding='utf-8',newline='\n')
    header_text=header.read_text().replace('int om_ieee80211_beacon_build_status','struct sk_buff;\nint om_ieee80211_beacon_frame_status(struct ieee80211_beacon_param_t *param, struct sk_buff *skb);\nint om_ieee80211_beacon_build_status',1)
    header.write_text(header_text,encoding='utf-8',newline='\n')
    desc.write_text(new,encoding='utf-8',newline='\n')
    beacon=wlan/'ieee80211_beacon.c';old=beacon.read_text();touched[str(beacon.relative_to(a.output))]=old;new=old
    start,end,body=function(new,'void\nieee80211_beacon_update(')
    validate='''\tIEEE80211_LOCK(ic);
\tif (om_ieee80211_beacon_frame_status(vap->param, skb))
\t\tgoto om_beacon_update_end;
\t/* Dynamic extents must match the current unpublished frame before writes. */
\t{
\t\tuintptr_t begin = (uintptr_t)skb->data;
\t\tuintptr_t end = begin + skb->len;
\t\tuintptr_t cca = (uintptr_t)bo->bo_cca;
\t\tuintptr_t app = (uintptr_t)bo->bo_appie_buf;
\t\tunsigned int cca_size = vap->param->om_cca_ie->size;
\t\tunsigned int app_size = vap->param->om_app_ie->size;
\t\tif (end < begin || cca < begin || cca > end || app < cca || app > end ||
\t\t    cca_size > end - cca || app != cca + cca_size ||
\t\t    bo->bo_appie_buf_len > end - app ||
\t\t    (app_size && app_size != bo->bo_appie_buf_len)) {
\t\t\tvap->param->om_build_error = -EINVAL;
\t\t\tgoto om_beacon_update_end;
\t\t}
\t}
'''
    body=body.replace('\tIEEE80211_LOCK(ic);',validate,1)
    marker='\t\tif (ic->ic_flags & IEEE80211_F_CCA) {';s,e,legacy=function(body,marker)
    body=body[:s]+CCA_UPDATE+'\n#if 0 /* Preserve original repeated-allocation algorithm. */\n'+legacy+'\n#endif\n'+body[e:]
    marker='\tif ((vap->app_ie[IEEE80211_APPIE_FRAME_BEACON].length != 0)';s,e,legacy=function(body,marker)
    body=body[:s]+APP_UPDATE+'\n#if 0 /* Preserve original APP allocation algorithm. */\n'+legacy+'\n#endif\n'+body[e:]
    body=body.replace('\tIEEE80211_UNLOCK(ic);','om_beacon_update_end:\n\tIEEE80211_UNLOCK(ic);',1)
    new=new[:start]+body+new[end:]
    new=new.replace('\tfrm = ieee80211_beacon_init(ni, bo, frm);','\tfrm = ieee80211_beacon_init(ni, bo, frm);\n\tif (om_ieee80211_beacon_build_status(vap->param)) {\n\t\tdev_kfree_skb_any(skb);\n\t\treturn NULL;\n\t}',1)
    new=new.replace('\tieee80211_add_beacon_desc_header(ni, (uint8_t *) wh);','\tieee80211_add_beacon_desc_header(ni, (uint8_t *) wh);\n\tif (om_ieee80211_beacon_build_status(vap->param)) {\n\t\tdev_kfree_skb_any(skb);\n\t\treturn NULL;\n\t}',1)
    beacon.write_text(new,encoding='utf-8',newline='\n')
    qc=qdrv/'qdrv_wlan.c';old=qc.read_text();touched[str(qc.relative_to(a.output))]=old
    marker='\tieee80211_beacon_update(ni, &qv->qv_boff, beacon_skb, 0);';assert old.count(marker)==1
    qc.write_text(old.replace(marker,marker+'''\n\t{
\t\tint build_error = om_ieee80211_beacon_frame_status(vap->param, beacon_skb);
\t\tif (build_error) {
\t\t\tqdrv_hostlink_free_coherent(NULL, sizeof(*bc_args), bc_args, args_dma);
\t\t\tvnet_free_ioctl(ioctl);
\t\t\tieee80211_beacon_destroy_param(vap);
\t\t\tdev_kfree_skb_any(beacon_skb);
\t\t\treturn build_error;
\t\t}
\t}''',1),encoding='utf-8',newline='\n')
    patches=[];comment_counts={}
    for rel,old in touched.items():
        path=a.output/rel;raw_before=old.encode();raw_after=path.read_bytes()
        old_comments=Counter(raw_before[b['offset']:b['end_offset']] for b in scan_comments(raw_before))
        new_comments=Counter(raw_after[b['offset']:b['end_offset']] for b in scan_comments(raw_after))
        assert not old_comments-new_comments, 'original comments lost: '+rel
        comment_counts[rel]=sum(old_comments.values())
        patches.append(''.join(difflib.unified_diff(old.splitlines(True),path.read_text().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel)))
    (a.output/'beacon-descriptor-lifetime.patch').write_text(''.join(patches),encoding='utf-8')
    init_text=function(beacon.read_text(),'static uint8_t *\nieee80211_beacon_init(')[2]
    static_calls=init_text.count('ieee80211_add_beacon_desc_ie(')+1+1
    result={'schema':'openmitrastar.beacon-descriptor-lifetime/v1','status':'SOURCE_ONLY_GLOBAL_BEACON_BUDGET_PENDING_FULL_MODULE',
            'hardware_accessed':False,'firmware_eligible':False,'parent_manifest_sha256':sha(a.parent/'result.json'),
            'changed_sources':{rel:sha(a.output/rel) for rel in touched},'original_comment_occurrences_preserved':comment_counts,
            'fixed_arena_bytes':1000,'descriptor_wire_bytes':20,'reserved_dynamic_slots':2,
            'static_source_call_upper_bound':static_calls,'total_descriptor_upper_bound':static_calls+2,
            'dynamic_behavior':'CCA/APP slot reused; removal unlinks only reserved descriptor; payload extent uses current lengths/tailroom',
            'publication_failure':'Construction errors cleaned up by QDRV before vnet_send_ioctl_owned',
            'constraints':['Host param append requires complete QDRV/WLAN/header-user rebuild.',
                'Preserved disabled legacy code is provenance, not a second compiled implementation.',
                'Wire descriptor and fixed1000B arena unchanged; actualARC layout unproved until compiler is available.',
                'Whole source function fixture and prepublication integration checks required; no physical/radio acceptance.']}
    assert (static_calls+2)*20 <=1000
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))
    return 0
if __name__=='__main__':raise SystemExit(main())
