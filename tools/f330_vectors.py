"""Concrete raw fixtures, independently checked against QEMU input hashes."""
import struct
def pulse(start,stop,power,tag=0):return {'start':start,'stop':stop,'max_power':power,'tagged':tag}
CASES={
 'history_a':[pulse(0,20,2),pulse(1000,1020,3),pulse(2000,2020,4)],
 'history_b':[pulse(5000,5030,5),pulse(7000,7030,6)],
 'history_c':[pulse(9000,9040,7)],'history_empty':[],'history_flush':[],
 'cross_a':[pulse(10,30,3)],'cross_b':[pulse(100,130,4)],
 'merge':[pulse(0,20,2),pulse(100,120,9),pulse(1000,1040,5)],
 'filters':[pulse(0,1,5),pulse(1000,1400,5),pulse(2000,2030,0),pulse(3000,3040,3),pulse(4000,4030,4)],
 'tag_replace':[pulse(0,20,3,1),pulse(1000,1040,4),pulse(2000,2040,5,1)],
 'terminal_tag_disabled':[pulse(0,40,3,1)],
 'epoch':[pulse(10,40,2),pulse(1000,1040,4)],
 'wrap_merge':[pulse(0x07ffffe0,0x07fffff0,2),pulse(5,25,9)],
 'limit_a':[pulse(i*1000,i*1000+40,2) for i in range(128)],
 'limit_b':[pulse(200000+i*1000,200040+i*1000,3) for i in range(128)],
 'quiet_100':[],'quiet_101':[],'pending_blocked':[],
 'confirmed_epoch':[pulse(10,50,2)],'busy_160':[pulse(0,40,2)],
 'busy_161':[pulse(1000,1040,2)],'failed_backend_blocked':[],
 'oversize_refused':None,'stale_refused':[],
}
def input_hash(raw):
    if raw is None:return 0
    h=2166136261
    for p in raw:
        for b in struct.pack('<IIIB3x',p['start'],p['stop'],p['max_power'],p['tagged']):h=((h^b)*16777619)&0xffffffff
    return h
