/* SPDX-License-Identifier: GPL-2.0-only
 * Exact declarations extracted from the OEM shared headers; pins in source manifest. */
#ifndef F367R5_IOCTL_H
#define F367R5_IOCTL_H
#define __packed __attribute__((packed))
#define	IEEE80211_CHAN_MAX	255
#define	IEEE80211_CHAN_BYTES	32	/* howmany(IEEE80211_CHAN_MAX, NBBY) */
#define IEEE80211_CHAN_DFS	0x00100000	/* Configuration: DFS-required channel */
#define IEEE80211_CHAN_PASSIVE	0x00000200	/* Only passive scan allowed */
#define	IEEE80211_IOCTL_GETPARAM	(SIOCIWFIRSTPRIV+1)
#define	IEEE80211_IOCTL_GETCHANLIST	(SIOCIWFIRSTPRIV+7)
#define	IEEE80211_IOCTL_GETCHANINFO	(SIOCIWFIRSTPRIV+13)
#define IEEE80211_IOCTL_EXT		(SIOCDEVPRIVATE+0xF) /* This command is used to support sub-ioctls */
#define SIOCDEV_SUBIO_BASE		(0)
#define SIOCDEV_SUBIO_SET_MARK_DFS_CHAN	(SIOCDEV_SUBIO_BASE + 14)
#define IEEE80211_PARAM_REGULATORY_REGION 115
struct ieee80211req_chanlist {
	uint8_t ic_channels[IEEE80211_CHAN_BYTES];
};
struct ieee80211_chan {
	uint16_t ic_freq;	/* Freq setting in Mhz */
	uint32_t ic_flags;	/* Channel flags */
	uint8_t ic_ieee;	/* IEEE channel number */
} __packed;
struct ieee80211req_chaninfo {
	uint32_t ic_nchans;
	struct ieee80211_chan ic_chans[IEEE80211_CHAN_MAX];
};
_Static_assert(sizeof(int)==4,"OEM int wire size");
_Static_assert(sizeof(struct ieee80211_chan)==7,"OEM packed channel size");
_Static_assert(offsetof(struct ieee80211_chan,ic_flags)==2,"OEM channel flags offset");
_Static_assert(offsetof(struct ieee80211req_chaninfo,ic_chans)==4,"OEM table offset");
_Static_assert(sizeof(struct ieee80211req_chaninfo)==1792,"OEM table size");
#if defined(__arc__)
_Static_assert(sizeof(struct iwreq)==32,"ARC iwreq size");
_Static_assert(offsetof(struct iwreq,u.data.length)==20,"ARC iw_point length");
_Static_assert(offsetof(struct iwreq,u.data.flags)==22,"ARC iw_point flags");
#endif
#endif
