// SPDX-License-Identifier: GPL-2.0-only
#include <linux/module.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/mutex.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <linux/wait.h>
#include <linux/jiffies.h>
#include <linux/capability.h>
#include <linux/poll.h>
#include "f338_ipc.h"
static DEFINE_MUTEX(ipc_lock);
static DECLARE_WAIT_QUEUE_HEAD(changed);
static struct f338_protocol protocol;
static struct f338_job *queued_job;
static struct f338_reply *completed_reply;
static void (*notify_loss)(unsigned);
static bool closing;
static unsigned terminal_reason;
struct f338_file {unsigned session;};
static unsigned now_ms(void){return jiffies_to_msecs(jiffies);}
static int valid_file(struct f338_file*f)
{return f&&f->session==protocol.session&&protocol.state!=F338_OFF;}
static int proto_errno(int rc)
{return rc==F338_PROTO_TIMEOUT?-ETIMEDOUT:rc==F338_PROTO_STALE?-ESTALE:rc==F338_PROTO_BUSY?-EBUSY:rc==F338_PROTO_EXHAUSTED?-EOVERFLOW:-EPROTO;}
static int device_open(struct inode*inode,struct file*file)
{
 struct f338_file *f;int rc;(void)inode;
 if(!capable(CAP_SYS_ADMIN))return -EPERM;
 f=kzalloc(sizeof(*f),GFP_KERNEL);if(!f)return -ENOMEM;
 mutex_lock(&ipc_lock);rc=closing?-ENODEV:f338_protocol_attach(&protocol);
 if(!rc){f->session=protocol.session;file->private_data=f;terminal_reason=0;}
 mutex_unlock(&ipc_lock);if(rc){kfree(f);return rc==-ENODEV?rc:proto_errno(rc);}
 wake_up_all(&changed);return nonseekable_open(inode,file);
}
static int device_release(struct inode*inode,struct file*file)
{
 struct f338_file*f=file->private_data;bool loss=false;(void)inode;
 mutex_lock(&ipc_lock);
 if(valid_file(f)){f338_protocol_detach(&protocol,f->session);loss=true;}
 mutex_unlock(&ipc_lock);wake_up_all(&changed);
 if(loss&&notify_loss)notify_loss(F338_SERVICE_CLOSED);
 kfree(f);return 0;
}
static ssize_t device_read(struct file*file,char __user*buf,size_t count,loff_t*off)
{
 struct f338_file*f=file->private_data;struct f338_job *copy;int rc;(void)off;
 if(count!=sizeof(*copy))return -EMSGSIZE;
 copy=kmalloc(sizeof(*copy),GFP_KERNEL);if(!copy)return -ENOMEM;
 for(;;){
  mutex_lock(&ipc_lock);
  if(!valid_file(f)||protocol.state==F338_ABORTED||closing){rc=-EPIPE;mutex_unlock(&ipc_lock);break;}
  if(protocol.state==F338_QUEUED){*copy=*queued_job;mutex_unlock(&ipc_lock);
   /* User faults cannot hold ipc_lock and delay the worker's PM deadline. */
   if(copy_to_user(buf,copy,sizeof(*copy))){rc=-EFAULT;break;}
   mutex_lock(&ipc_lock);rc=f338_protocol_delivered(&protocol,&copy->h,now_ms());mutex_unlock(&ipc_lock);
   rc=rc?proto_errno(rc):sizeof(*copy);wake_up_all(&changed);break;
  }
  mutex_unlock(&ipc_lock);
  if(file->f_flags&O_NONBLOCK){rc=-EAGAIN;break;}
  rc=wait_event_interruptible(changed,READ_ONCE(protocol.state)==F338_QUEUED||READ_ONCE(protocol.state)==F338_OFF||READ_ONCE(protocol.state)==F338_ABORTED||READ_ONCE(closing));
  if(rc)break;
 }
 kfree(copy);return rc;
}
static ssize_t device_write(struct file*file,const char __user*buf,size_t count,loff_t*off)
{
 struct f338_file*f=file->private_data;struct f338_reply*r;int rc;bool loss=false;(void)off;
 if(count!=sizeof(*r))return -EMSGSIZE;
 r=memdup_user(buf,sizeof(*r));if(IS_ERR(r))return PTR_ERR(r);
 mutex_lock(&ipc_lock);
 rc=valid_file(f)?f338_protocol_reply(&protocol,r,now_ms()):F338_PROTO_STALE;
 if(!rc)*completed_reply=*r;
 else if(rc!=F338_PROTO_STALE){f338_protocol_abort(&protocol);terminal_reason=rc==F338_PROTO_TIMEOUT?F338_SERVICE_TIMEOUT:F338_SERVICE_PROTOCOL;loss=true;}
 mutex_unlock(&ipc_lock);kfree(r);wake_up_all(&changed);
 if(loss&&notify_loss)notify_loss(rc==F338_PROTO_TIMEOUT?F338_SERVICE_TIMEOUT:F338_SERVICE_PROTOCOL);
 return rc?proto_errno(rc):count;
}
static long device_ioctl(struct file*file,unsigned cmd,unsigned long arg)
{
 struct f338_file*f=file->private_data;struct f338_reset request,cached;
 struct f338_header hello;int rc;unsigned n;
 if(cmd==F338_IOC_HELLO){
  mutex_lock(&ipc_lock);rc=valid_file(f)?0:-EPIPE;
  memset(&hello,0,sizeof(hello));hello.magic=F338_MAGIC;hello.abi=F338_ABI;hello.size=sizeof(hello);hello.session=protocol.session;
  mutex_unlock(&ipc_lock);if(rc)return rc;
  return copy_to_user((void __user*)arg,&hello,sizeof(hello))?-EFAULT:0;
 }
 if(cmd!=F338_IOC_RESET)return -ENOTTY;
 if(copy_from_user(&request,(void __user*)arg,sizeof(request)))return -EFAULT;
 mutex_lock(&ipc_lock);
 rc=valid_file(f)?f338_protocol_reset_begin(&protocol,&request,&cached,now_ms()):F338_PROTO_STALE;
 if(rc==F338_PROTO_BUSY&&protocol.reset_pending==request.request_id)rc=0;
 mutex_unlock(&ipc_lock);
 if(rc==F338_PROTO_REPLAY)return copy_to_user((void __user*)arg,&cached,sizeof(cached))?-EFAULT:0;
 if(rc)return proto_errno(rc);
 wake_up_all(&changed);
 /* The PM-owning worker does the two writes. No MMIO, BB, or provider
  * state_lock is held by this syscall while it waits for that result. */
 for(;;){
  rc=wait_event_interruptible_timeout(changed,READ_ONCE(protocol.reset_pending)!=request.request_id||READ_ONCE(protocol.state)!=F338_DELIVERED,msecs_to_jiffies(F338_DEADLINE_MS));
  if(rc<0)return rc;
  mutex_lock(&ipc_lock);
  if(!valid_file(f)||protocol.sequence!=request.h.sequence||protocol.generation!=request.h.generation){mutex_unlock(&ipc_lock);return -ESTALE;}
  for(n=0;n<protocol.reset_count;n++)if(protocol.resets[n].request_id==request.request_id)break;
  if(n<protocol.reset_count){cached=protocol.resets[n];mutex_unlock(&ipc_lock);return copy_to_user((void __user*)arg,&cached,sizeof(cached))?-EFAULT:0;}
  if(protocol.state==F338_ABORTED||!rc){mutex_unlock(&ipc_lock);return -ETIMEDOUT;}
  if(protocol.state!=F338_DELIVERED){mutex_unlock(&ipc_lock);return -ESTALE;}
  mutex_unlock(&ipc_lock);
 }
}
static __poll_t device_poll(struct file*file,poll_table*wait)
{
 __poll_t mask=0;poll_wait(file,&changed,wait);mutex_lock(&ipc_lock);
 if(!valid_file(file->private_data)||protocol.state==F338_ABORTED)mask=EPOLLERR|EPOLLHUP;
 else if(protocol.state==F338_QUEUED)mask=EPOLLIN|EPOLLRDNORM;
 else if(protocol.state==F338_DELIVERED)mask=EPOLLOUT|EPOLLWRNORM;
 mutex_unlock(&ipc_lock);return mask;
}
static const struct file_operations operations={.owner=THIS_MODULE,.open=device_open,.release=device_release,.read=device_read,.write=device_write,.unlocked_ioctl=device_ioctl,.poll=device_poll,.llseek=no_llseek};
static struct miscdevice device={.minor=MISC_DYNAMIC_MINOR,.name="om-radar-f338",.fops=&operations,.mode=0600};
int f338_ipc_init(void(*lost)(unsigned))
{
 int rc;BUILD_BUG_ON(sizeof(struct f338_header)!=24);BUILD_BUG_ON(sizeof(struct f338_job)!=24072);BUILD_BUG_ON(sizeof(struct f338_reply)!=1048);BUILD_BUG_ON(sizeof(struct f338_reset)!=40);
 queued_job=kzalloc(sizeof(*queued_job),GFP_KERNEL);completed_reply=kzalloc(sizeof(*completed_reply),GFP_KERNEL);
 if(!queued_job||!completed_reply){kfree(queued_job);kfree(completed_reply);return -ENOMEM;}
 notify_loss=lost;closing=false;rc=misc_register(&device);
 if(rc){kfree(queued_job);kfree(completed_reply);}return rc;
}
void f338_ipc_exit(void)
{
 mutex_lock(&ipc_lock);closing=true;f338_protocol_abort(&protocol);mutex_unlock(&ipc_lock);wake_up_all(&changed);
 misc_deregister(&device);kfree(queued_job);kfree(completed_reply);notify_loss=0;
}
int f338_ipc_available(void){int yes;mutex_lock(&ipc_lock);yes=!closing&&protocol.state!=F338_OFF&&protocol.state!=F338_ABORTED;mutex_unlock(&ipc_lock);return yes;}
void f338_ipc_wake(void){wake_up_all(&changed);}
void f338_ipc_cancel(void){mutex_lock(&ipc_lock);f338_protocol_cancel(&protocol);mutex_unlock(&ipc_lock);wake_up_all(&changed);}
int f338_ipc_exchange(struct f338_job*j,struct f338_reply*r,int(*is_current)(unsigned),int(*reset)(void*,unsigned,unsigned,int*,int*))
{
 int rc;unsigned reason=0,remaining;struct f338_reset response;
 mutex_lock(&ipc_lock);
 if(closing||protocol.state==F338_OFF||protocol.state==F338_ABORTED){mutex_unlock(&ipc_lock);return -ENOTCONN;}
 rc=f338_protocol_queue(&protocol,j,now_ms());if(!rc)*queued_job=*j;
 mutex_unlock(&ipc_lock);if(rc)return proto_errno(rc);wake_up_all(&changed);
 for(;;){
  mutex_lock(&ipc_lock);
  if(!is_current(j->h.generation)){f338_protocol_cancel(&protocol);rc=-ESTALE;goto done;}
  if(protocol.session!=j->h.session||protocol.state==F338_OFF){rc=-ENOTCONN;goto done;}
  if(f338_protocol_check_timeout(&protocol,now_ms())||protocol.state==F338_ABORTED){
   rc=terminal_reason==F338_SERVICE_PROTOCOL?-EPROTO:-ETIMEDOUT;
   if(!terminal_reason){terminal_reason=F338_SERVICE_TIMEOUT;reason=terminal_reason;}
   goto done;
  }
  if(protocol.state==F338_REPLY){*r=*completed_reply;rc=0;goto done;}
  if(protocol.reset_pending){
   memset(&response,0,sizeof(response));response.h=j->h;response.h.size=sizeof(response);response.request_id=protocol.reset_pending;
   mutex_unlock(&ipc_lock);
   rc=reset(0,j->h.generation,response.request_id,&response.actual_seconds,&response.actual_microseconds);
   mutex_lock(&ipc_lock);
   if(!is_current(j->h.generation)||rc==1){f338_protocol_cancel(&protocol);rc=-ESTALE;goto done;}
   if(rc){f338_protocol_abort(&protocol);reason=F338_HARDWARE_FAULT;rc=-EIO;goto done;}
   response.sequence_emitted=1;rc=f338_protocol_reset_end(&protocol,&response,now_ms());
   if(rc){f338_protocol_abort(&protocol);reason=F338_SERVICE_TIMEOUT;rc=proto_errno(rc);goto done;}
   mutex_unlock(&ipc_lock);wake_up_all(&changed);continue;
  }
  remaining=protocol.deadline_ms-now_ms();mutex_unlock(&ipc_lock);
  /* A generation setter can run in IRQ context: wake is lock-free, and
   * this bounded wait rechecks the actual request epoch before any MMIO. */
  wait_event_timeout(changed,READ_ONCE(protocol.reset_pending)||READ_ONCE(protocol.state)==F338_REPLY||READ_ONCE(protocol.state)==F338_OFF||READ_ONCE(protocol.state)==F338_ABORTED||!is_current(j->h.generation),msecs_to_jiffies(remaining>10?10:remaining)+1);
 }
done:
 mutex_unlock(&ipc_lock);wake_up_all(&changed);if(reason&&notify_loss)notify_loss(reason);return rc;
}
