/* Execute exactly one qualified F342 save on a private in-memory NOR image. */
#include "f342_journal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
static unsigned char store[0x20000];
static unsigned held,erases,programs;
static unsigned addresses[32],lengths[32];
static int claim(void *p){(void)p;if(held)return -1;held=1;return 0;}
static void release(void *p){(void)p;if(!held)abort();held=0;}
static int protect(void *p,uint32_t address,uint8_t *v){(void)p;(void)address;if(!held)return -1;*v=0;return 0;}
static int restore(void *p,uint32_t address,uint8_t v){(void)p;return held&&address==0xdc0000&&v==0?0:-1;}
static int erase(void *p,uint32_t address){(void)p;if(!held||address!=0xdc0000)return -1;memset(store,255,65536);erases++;return 0;}
static int program(void *p,uint32_t address,const uint8_t *bytes,size_t n)
{
 size_t i;uint32_t off=address-0xdc0000u;(void)p;
 if(!held||address<0xdc0000u||off>=65536u||!n||n>256u-(off&255u)||n>65536u-off||programs>=32)return -1;
 addresses[programs]=address;lengths[programs]=(unsigned)n;programs++;
 for(i=0;i<n;i++){if((store[off+i]&bytes[i])!=bytes[i])return -1;store[off+i]&=bytes[i];}
 return 0;
}
static int read_data(void *p,uint32_t address,uint8_t *bytes,size_t n)
{uint32_t off=address-0xdc0000u;(void)p;if(!held||address<0xdc0000u||off>sizeof(store)||n>sizeof(store)-off)return -1;memcpy(bytes,store+off,n);return 0;}
static int sync_data(void *p){(void)p;return held?0:-1;}
int main(int argc,char **argv)
{
 struct f318_store_ops ops={claim,release,protect,restore,erase,program,read_data,sync_data,NULL,0};
 struct f342_workspace workspace;struct f342_result result;unsigned char payload[4097];size_t n;FILE *file;unsigned i;
 if(argc!=3)return 2;
 umask(077);file=fopen(argv[1],"rb");if(!file)return 3;n=fread(payload,1,sizeof(payload),file);if(ferror(file)||fclose(file)||!n||n>4096)return 4;
 memset(store,255,sizeof(store));
 if(f342_save(&ops,&workspace,payload,n,&result)!=0||held||result.record.slot!=0||result.record.sequence!=1||!result.commit_visible||!result.protection_restored||!result.witnesses_unchanged||erases!=1)return 5;
 for(i=65536;i<sizeof(store);i++)if(store[i]!=255)return 6;
 file=fopen(argv[2],"wb");if(!file)return 7;
 if(fwrite(store,1,sizeof(store),file)!=sizeof(store)||fclose(file))return 8;
 printf("{\"save_calls\":1,\"slot\":0,\"sequence\":1,\"payload_bytes\":%zu,\"erase_calls\":%u,\"program_calls\":%u,\"programmed_bytes\":%zu,\"commit_visible\":true,\"protection_restored\":true,\"witnesses_unchanged\":true,\"operations\":[",n,erases,programs,result.programmed_bytes);
 for(i=0;i<programs;i++)printf("%s{\"address\":%u,\"bytes\":%u}",i?",":"",addresses[i],lengths[i]);
 puts("]}");memset(payload,0,sizeof(payload));return 0;
}
