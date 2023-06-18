(1) killsnoop_forall.sh 在killsnoop.sh的基础上做了简单改动，主要是为了监控[kill pid -1]。所以该脚本会忽略掉INT QUIT TERM PIPE HUP信号。
(2) 启动脚本后: "sh killsnoop_forall.sh -t -p 4294967295",进程如下：
sh(35305)-+-gawk(35308)
          `-sh(35307)---cat(35309)
执行"kill -9 35309"即可停止脚本运行

