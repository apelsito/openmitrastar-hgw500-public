/* Test the actual device file operations and exchange loop with POSIX threads.
 * Only MMIO callback is fake and asserts the PM-owning worker executes it. */
#include "ipc-under-test.c"
static unsigned checks,losses,last_reason,pm_refs,reset_writes;
static unsigned generation=1;
static pthread_t worker_thread;
static struct f338_job sent,received;
static struct f338_reply answer,outcome;
static struct file client;
static int exchange_result,read_result;
static unsigned reset_pause,reset_entered;
static struct f338_reset threaded_reset;
static int reset_ioctl_result;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"FAIL line%d: %s\n",__LINE__,#x);exit(1);}}while(0)
static void lost(unsigned reason){__atomic_add_fetch(&losses,1,__ATOMIC_SEQ_CST);__atomic_store_n(&last_reason,reason,__ATOMIC_SEQ_CST);}
static int current_generation(unsigned g){return g==READ_ONCE(generation);}
static int fake_reset(void*ctx,unsigned g,unsigned request,int*s,int*us)
{(void)ctx;(void)request;CHECK(pthread_equal(pthread_self(),worker_thread));CHECK(READ_ONCE(pm_refs)==1);__atomic_store_n(&reset_entered,1,__ATOMIC_SEQ_CST);while(READ_ONCE(reset_pause))usleep(1000);if(!current_generation(g))return 1;reset_writes+=2;*s=100;*us=42;return 0;}
static void *exchange(void*unused)
{(void)unused;worker_thread=pthread_self();__atomic_store_n(&pm_refs,1,__ATOMIC_SEQ_CST);exchange_result=f338_ipc_exchange(&sent,&outcome,current_generation,fake_reset);__atomic_store_n(&pm_refs,0,__ATOMIC_SEQ_CST);return 0;}
static void*slow_read(void*unused){(void)unused;read_result=device_read(&client,(char*)&received,sizeof(received),0);return 0;}
static void*thread_reset(void*unused){(void)unused;reset_ioctl_result=device_ioctl(&client,F338_IOC_RESET,(unsigned long)&threaded_reset);return 0;}
static void initialize_job(void)
{memset(&sent,0,sizeof(sent));sent.h.magic=F338_MAGIC;sent.h.abi=F338_ABI;sent.h.size=sizeof(sent);sent.h.generation=generation;sent.channel=52;sent.bandwidth=80;sent.real_seconds=100;}
static void start(pthread_t*t)
{initialize_job();CHECK(!pthread_create(t,0,exchange,0));while(READ_ONCE(protocol.state)!=F338_QUEUED)usleep(100);}
static void receive(void)
{CHECK(device_read(&client,(char*)&received,sizeof(received),0)==sizeof(received));memset(&answer,0,sizeof(answer));answer.h=received.h;answer.h.size=sizeof(answer);}
static void join(pthread_t t,int expected){CHECK(!pthread_join(t,0));CHECK(exchange_result==expected);CHECK(!READ_ONCE(pm_refs));}
int main(void)
{
 struct f341_ipc_stats snapshot;
 pthread_t thread,reader;struct f338_reset reset;unsigned before,old_sequence;struct file extra={0};
 CHECK(!f338_ipc_init(lost));CHECK(!device_open(0,&client));CHECK(device_open(0,&extra)==-EBUSY);
 start(&thread);receive();
 memset(&reset,0,sizeof(reset));reset.h=received.h;reset.h.size=sizeof(reset);reset.request_id=1;
 CHECK(!device_ioctl(&client,F338_IOC_RESET,(unsigned long)&reset));CHECK(reset.sequence_emitted==1&&reset.actual_microseconds==42&&reset_writes==2);
 CHECK(!device_ioctl(&client,F338_IOC_RESET,(unsigned long)&reset));CHECK(reset_writes==2);
 answer.reset_sequences=1;CHECK(device_write(&client,(char*)&answer,sizeof(answer),0)==sizeof(answer));join(thread,0);
 /* Cancel before delivery then a valid later sequence. */
 start(&thread);old_sequence=sent.h.sequence;__atomic_add_fetch(&generation,1,__ATOMIC_SEQ_CST);f338_ipc_wake();join(thread,-ESTALE);
 start(&thread);receive();CHECK(received.h.sequence==old_sequence+1);CHECK(device_write(&client,(char*)&answer,sizeof(answer),0)==sizeof(answer));join(thread,0);
 /* Cancel after delivery: late math cannot publish to a new generation. */
 start(&thread);receive();__atomic_add_fetch(&generation,1,__ATOMIC_SEQ_CST);f338_ipc_wake();join(thread,-ESTALE);
 CHECK(device_write(&client,(char*)&answer,sizeof(answer),0)==-ESTALE);
 start(&thread);receive();CHECK(device_write(&client,(char*)&answer,sizeof(answer),0)==sizeof(answer));join(thread,0);
 /* Cancellation while reset is being dispatched. PM belongs to worker,
  * stale reset emits no writes and the next generation remains usable. */
 start(&thread);receive();memset(&threaded_reset,0,sizeof(threaded_reset));threaded_reset.h=received.h;threaded_reset.h.size=sizeof(threaded_reset);threaded_reset.request_id=7;
 reset_pause=1;reset_entered=0;before=reset_writes;CHECK(!pthread_create(&reader,0,thread_reset,0));while(!READ_ONCE(reset_entered))usleep(100);
 __atomic_add_fetch(&generation,1,__ATOMIC_SEQ_CST);f338_ipc_wake();CHECK(READ_ONCE(pm_refs)==1);reset_pause=0;
 join(thread,-ESTALE);CHECK(!pthread_join(reader,0));CHECK(reset_ioctl_result==-ESTALE&&reset_writes==before);
 start(&thread);receive();CHECK(device_write(&client,(char*)&answer,sizeof(answer),0)==sizeof(answer));join(thread,0);
 /* User copy deliberately stalls. Worker deadline still releases PM. */
 start(&thread);copy_entered=0;copy_pause=1;CHECK(!pthread_create(&reader,0,slow_read,0));while(!READ_ONCE(copy_entered))usleep(100);
 join(thread,-ETIMEDOUT);CHECK(last_reason==F338_SERVICE_TIMEOUT);copy_pause=0;CHECK(!pthread_join(reader,0));CHECK(read_result<0);
 CHECK(!device_release(0,&client));CHECK(!device_open(0,&client));
 /* Consumer close while PM transaction waits; no lingering reference. */
 start(&thread);before=losses;CHECK(!device_release(0,&client));join(thread,-ENOTCONN);CHECK(losses==before+1&&last_reason==F338_SERVICE_CLOSED);
 CHECK(!device_open(0,&client));start(&thread);receive();answer.h.magic=0;
 CHECK(device_write(&client,(char*)&answer,sizeof(answer),0)==-EPROTO);join(thread,-EPROTO);CHECK(protocol.state==F338_ABORTED&&last_reason==F338_SERVICE_PROTOCOL);
 f341_ipc_snapshot(&snapshot);
 CHECK(snapshot.jobs_completed==4&&snapshot.jobs_cancelled==3&&snapshot.timeouts==1&&snapshot.protocol_errors==1);
 CHECK(snapshot.reset_sequences==1&&snapshot.reset_replays==1&&snapshot.hardware_errors==0);
 CHECK(snapshot.max_latency_ms>=F338_DEADLINE_MS&&snapshot.state==F338_ABORTED);
 CHECK(!device_release(0,&client));f338_ipc_exit();
 printf("F338_IPC_ACTUAL_PASS checks=%u fake_reset_writes=%u hardware=0\n",checks,reset_writes);return 0;
}
