"""Versioned host-ABI policy hook for CSA before software/hardware retune."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f332-peers-20260921T121519Z/source'
PEERS=ROOT/'work/linux510-radio-port/quantenna-f344-peers'
QDRV=ROOT/'work/linux510-radio-port/quantenna-f344-modes/qdrv'
HEADERS=ROOT/'work/kernel-port/f344/headers/net80211'
def closing(text,start):
 i=text.index('{',start)+1;depth=1
 while depth:
  if text.startswith('/*',i):i=text.index('*/',i+2)+2;continue
  if text.startswith('//',i):i=text.index('\n',i+2)+1;continue
  if text[i] in ('"',"'"):
   quote=text[i];i+=1
   while text[i]!=quote:i+=2 if text[i]=='\\' else 1
   i+=1;continue
  depth+=(text[i]=='{')-(text[i]=='}');i+=1
 return i-1
def main():
 if PEERS.exists() or HEADERS.exists():raise SystemExit('F344 CSA source already exists')
 shutil.copytree(BASE,PEERS);HEADERS.mkdir(parents=True)
 original=ROOT/'work/sources/Quantenna-GPL/drivers/include/kernel/net80211/ieee80211_var.h'
 source=original.read_text();start=source.index('struct ieee80211com {');end=closing(source,start)
 source=source[:end]+'''\n\t/* F344 host-only extension. All qdrv/wlan peers share this ABI. */
\tint (*ic_f344_channel_allowed)(struct ieee80211com *, struct ieee80211_channel *);
'''+source[end:]
 source+='\nextern unsigned ieee80211_f344_policy_abi_v1(void);\n'
 (HEADERS/'ieee80211_var.h').write_bytes(source.encode())
 p=PEERS/'wlan/ieee80211.c';s=p.read_text();s+='''
unsigned ieee80211_f344_policy_abi_v1(void)
{
 return sizeof(struct ieee80211com);
}
EXPORT_SYMBOL_GPL(ieee80211_f344_policy_abi_v1);
''';p.write_bytes(s.encode())
 p=PEERS/'wlan/ieee80211_wireless.c';s=p.read_text()
 start=s.index('void\nieee80211_finish_csa(') if 'void\nieee80211_finish_csa(' in s else s.index('void ieee80211_finish_csa(')
 body=s.index('{',start);anchor=s.index('\n\tif ',body)
 s=s[:anchor]+'''
\t/* Reject before CAC bookkeeping or any channel-pointer change. This
\t * timer is joined by the mode transition before software state is reset. */
\tif (ic->ic_f344_channel_allowed &&
\t    !ic->ic_f344_channel_allowed(ic, ic->ic_csa_chan)) {
\t\tic->ic_csa_count = 0;
\t\tic->ic_flags &= ~IEEE80211_F_CHANSWITCH;
\t\treturn;
\t}
'''+s[anchor:]
 start=s.index('int ieee80211_enter_csa(');anchor=s.index('\n\tif (ic->ic_flags & IEEE80211_F_CHANSWITCH)',start)
 s=s[:anchor]+'''
\tif (ic->ic_f344_channel_allowed && !ic->ic_f344_channel_allowed(ic, chan))
\t\treturn -EPERM;
'''+s[anchor:];p.write_bytes(s.encode())
 p=PEERS/'wlan/ieee80211_input.c';s=p.read_text()
 # Existing active-list test dominates all subsequent CSA publication.
 needle='if (isclr(ic->ic_chan_active, chan))'
 if needle not in s:
  needle='if (isclr(ic->ic_chan_active, csaie->csa_chan))'
 # The exact source is inspected below if its syntax differs; never guess.
 if needle not in s:
  (PEERS/'CSA_INPUT_PENDING.txt').write_text('Needs policy hook adjacent to parse_csaie active-list guard; native active-list guard remains intact.\n')
 else:
  # Defer selector expression binding to the reviewed function body, not an
  # unchecked textual rewrite across unrelated scan-channel predicates.
  (PEERS/'CSA_INPUT_PENDING.txt').write_text('Native active-list guard present; enter/finish + final driver guards installed. Review received-deferred path separately.\n')
 p=QDRV/'qdrv_wlan.c';s=p.read_text();needle='ic->ic_set_channel = qdrv_set_channel;'
 if needle not in s:raise ValueError('ic_set_channel assignment anchor missing')
 s=s.replace(needle,needle+'\n\tic->ic_f344_channel_allowed = qdrv_f344_deferred_channel_allowed;',1);p.write_bytes(s.encode())
 p=QDRV/'qdrv_control.c';s=p.read_text();needle='qw=qdrv_mac_get_wlan(mac);view->core_started=!!openmitrastar_sequential_started;'
 if needle not in s:raise ValueError('topology ABI check anchor missing')
 s=s.replace(needle,'qw=qdrv_mac_get_wlan(mac);if(ieee80211_f344_policy_abi_v1()!=sizeof(qw->ic))return -EPROTO;view->core_started=!!openmitrastar_sequential_started;',1)
 s=s.replace('||qw->ic.ic_csa_count!=0;','||qw->ic.ic_csa_count!=0||timer_pending(&qw->ic.ic_timer_csa)||!!(qw->ic.ic_flags&IEEE80211_F_CHANSWITCH);',1);p.write_bytes(s.encode())
 (HEADERS.parent/'provenance.json').write_text(json.dumps({'original_header':str(original),'original_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'host_only_field':True,'requires_coherent_26_module_rebuild':True,'hardware':False},indent=2)+'\n')
if __name__=='__main__':main()
