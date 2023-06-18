#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <string.h>

unsigned long long get_cgroup_id (char *container_pathname)
{
    int dirfd = 0, flags = 0, mount_id = 0, fhsize = 0;
    struct file_handle *fhp = NULL;
    unsigned long long cgroup_id = 0;
    int err = 0;

    /// get container id info
    dirfd = AT_FDCWD;
    flags = 0;

    fhsize = sizeof(struct file_handle);
    fhp = malloc(fhsize);

    if(!fhp) {
        perror("malloc fail\n");
        return -1;
    }

    err = name_to_handle_at(dirfd, container_pathname, fhp, &mount_id, flags);
    if (err >= 0){
        perror("name_to_handle_at syscall fails to get handle_size\n");
        return -1;
    }

    fhsize = sizeof(struct file_handle) + fhp->handle_bytes;
    fhp = realloc(fhp, fhsize);

    if(!fhp) {
        perror("malloc fail\n");
        return -1;
    }

    err = name_to_handle_at(dirfd, container_pathname, fhp, &mount_id, flags);

    if (err < 0){
        perror("name_to_handle_at syscall fails to get handle info\n");
        free(fhp);
        return -1;
    }

    if (fhp->handle_bytes != 8) {
        free(fhp);
        return -1;
    }

    cgroup_id =  *(unsigned long long *)fhp->f_handle;

    free(fhp);

    return cgroup_id;
}

void help() {
    printf("usage:get container_id fron container path\n");
    printf("-p cgroup path for container, need start from '/cgroups/'\n");
    printf("-d print containe_id for debug\n");
}

int main (int argc, char **argv)
{
    char *container_cgroup_path = NULL;
    unsigned long long cgroup_id = 0;
    const char *opt_str = "p:hd";
    bool debug = false;
    int opt = 0, err = 0;

    if (argc <= 1){
        help();
        return 0;
    }

    while ((opt = getopt(argc, argv, opt_str)) != -1) {
        switch (opt) {
        case 'p':
            container_cgroup_path = optarg;
            break;
        case 'h':
            help();
            return 0;
	case 'd':
	    debug = true;
        default:
            continue;
        }
    }

    if (container_cgroup_path == NULL) {
        perror("container cgroup path is null\n");
        return -1;
    }
 
    err = strncmp(container_cgroup_path, "/cgroups", 8);
    if (err != 0) {
    	perror("container pathname is not cgroup dir\n");
    	return -1;
    }

    cgroup_id = get_cgroup_id(container_cgroup_path);
    if (cgroup_id < 0) {
    	err = cgroup_id;
	perror("fail to get cgroup id \n");
	return err;
    }

    if (debug)
       printf("%s:%lld\n", container_cgroup_path, cgroup_id);

    return cgroup_id;
}
