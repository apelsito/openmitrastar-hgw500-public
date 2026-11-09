/* Test only: Linux syscall synchronization facade, no physical hardware. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <time.h>
#include <unistd.h>
#include <sys/epoll.h>
#include <sys/types.h>
#define __user
#define GFP_KERNEL 0
#define THIS_MODULE 0
#define CAP_SYS_ADMIN 1
#define MISC_DYNAMIC_MINOR 0
#define BUILD_BUG_ON(x) _Static_assert(!(x),#x)
#define DEFINE_MUTEX(n) pthread_mutex_t n=PTHREAD_MUTEX_INITIALIZER
#define mutex_lock(m) pthread_mutex_lock(m)
#define mutex_unlock(m) pthread_mutex_unlock(m)
#define READ_ONCE(v) __atomic_load_n(&(v),__ATOMIC_SEQ_CST)
struct test_wait_queue {pthread_mutex_t lock;pthread_cond_t cond;};
#define DECLARE_WAIT_QUEUE_HEAD(n) struct test_wait_queue n={PTHREAD_MUTEX_INITIALIZER,PTHREAD_COND_INITIALIZER}
static unsigned shim_ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (unsigned)((uint64_t)t.tv_sec*1000+t.tv_nsec/1000000);}
#define jiffies shim_ms()
#define jiffies_to_msecs(x) (x)
#define msecs_to_jiffies(x) (x)
static struct timespec shim_deadline(unsigned ms){struct timespec t;clock_gettime(CLOCK_REALTIME,&t);t.tv_sec+=ms/1000;t.tv_nsec+=(ms%1000)*1000000;if(t.tv_nsec>=1000000000){t.tv_sec++;t.tv_nsec-=1000000000;}return t;}
static void wake_up_all(struct test_wait_queue*q){pthread_mutex_lock(&q->lock);pthread_cond_broadcast(&q->cond);pthread_mutex_unlock(&q->lock);}
#define wait_event_timeout(q,condition,ms) ({long result=1;struct timespec deadline=shim_deadline(ms);pthread_mutex_lock(&(q).lock);while(!(condition)){if(pthread_cond_timedwait(&(q).cond,&(q).lock,&deadline)==ETIMEDOUT){result=0;break;}}pthread_mutex_unlock(&(q).lock);result;})
#define wait_event_interruptible_timeout(q,condition,ms) wait_event_timeout(q,condition,ms)
#define wait_event_interruptible(q,condition) ({pthread_mutex_lock(&(q).lock);while(!(condition))pthread_cond_wait(&(q).cond,&(q).lock);pthread_mutex_unlock(&(q).lock);0;})
static void*kzalloc(size_t n,int flags){(void)flags;return calloc(1,n);}
static void*kmalloc(size_t n,int flags){(void)flags;return malloc(n);}
#define kfree free
static void*memdup_user(const void*p,size_t n){void*q=malloc(n);if(q)memcpy(q,p,n);return q;}
#define IS_ERR(p) (!(p))
#define PTR_ERR(p) (-ENOMEM)
static volatile unsigned copy_pause,copy_entered;
static int copy_to_user(void*dst,const void*src,size_t n){__atomic_store_n(&copy_entered,1,__ATOMIC_SEQ_CST);while(READ_ONCE(copy_pause))usleep(1000);memcpy(dst,src,n);return 0;}
static int copy_from_user(void*dst,const void*src,size_t n){memcpy(dst,src,n);return 0;}
struct inode {int unused;};
struct file {void*private_data;unsigned f_flags;};
typedef unsigned __poll_t;
typedef void poll_table;
struct file_operations {void*owner;int(*open)(struct inode*,struct file*);int(*release)(struct inode*,struct file*);ssize_t(*read)(struct file*,char*,size_t,loff_t*);ssize_t(*write)(struct file*,const char*,size_t,loff_t*);long(*unlocked_ioctl)(struct file*,unsigned,unsigned long);__poll_t(*poll)(struct file*,poll_table*);void*llseek;};
struct miscdevice {unsigned minor;const char*name;const struct file_operations*fops;unsigned mode;};
static int capable(int cap){(void)cap;return 1;}
static int nonseekable_open(struct inode*i,struct file*f){(void)i;(void)f;return 0;}
#define no_llseek 0
static void poll_wait(struct file*f,struct test_wait_queue*q,poll_table*w){(void)f;(void)q;(void)w;}
static int misc_register(struct miscdevice*d){(void)d;return 0;}
static void misc_deregister(struct miscdevice*d){(void)d;}
