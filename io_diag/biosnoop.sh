#!/bin/bash
count=1
duration=1441
max_avg_lat=0
sleep_time=50 
afs_instance=`ls /matrix/run/container | grep AFS`

while [ $count -lt $duration ]
do
	echo > ./afs_io_tmp
	ex_time=`expr 60 - $sleep_time`
	./src/biosnoop.py -c $afs_instance -o ./afs_io_tmp -t $ex_time -m
	total_ios=`cat ./afs_io_tmp | grep total_ios | awk -F ':' '{print $2}' | sed 's/,/ /g' |  awk '{sum += $1} END {print sum}'`
	total_lat=`cat ./afs_io_tmp | grep total_lat | awk -F ':' '{print $2}' | sed 's/,/ /g' |  awk '{sum += $1} END {print sum}'`
	if [[ $total_ios -gt 0 ]];then
		avg_lat=`expr $total_lat / $total_ios`
	else
		avg_lat=0
	fi
	
	if [[ $avg_lat -gt $max_avg_lat ]];then
   		max_avg_lat=$avg_lat
	fi
	
	cnt_is_10=`expr $count % 10`
	if [[ $cnt_is_10 -eq 0 ]];then
		data_cur=`date +%Y-%m-%d-%H:%M:%S` 
		echo $afs_instance $data_cur "max_avg_lat(ms)="$max_avg_lat >> ./afs_avg_iolat
		max_avg_lat=0
	fi

	sleep $sleep_time

	let count=$count+1
done
