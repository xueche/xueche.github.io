#！/bin/bash
# $1: the container name

CGROUP_PATH="/cgroups/v2"

if [ -d $CGROUP_PATH ];then
	CONTAINER_PATH=`find $CGROUP_PATH -name $1`
	if [ -n $CONTAINER_PATH ]; then
		echo -n  $CONTAINER_PATH
	fi
fi
