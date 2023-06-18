#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <string.h>

#define STRING_LENGTH_MAX 1000
#define config_file "/tmp/container_config"

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
    printf("usage: -cpg\n");
    printf("-c container name \n");
    printf("-p opcode, include 'add' and 'del' for container config update\n");
    printf("-g cgroup path for container, need start from '/cgroups/'\n");
}

int main (int argc, char **argv)
{
    char *container_cgroup_path = NULL, *container_name = NULL;
    unsigned long long cgroup_id = 0;
    char *opcode = NULL;
    const char *opt_str = "c:g:p:h";
    int opt = 0, err = 0;

    if (argc <= 1){
        help();
        return 0;
    }

    while ((opt = getopt(argc, argv, opt_str)) != -1) {
        switch (opt) {
        case 'c':
            container_name = optarg;
            break;
        case 'p':
            opcode = optarg;
            break;
        case 'g':
            container_cgroup_path = optarg;
            break;
        case 'h':
            help();
            return 0;
        default:
            continue;
        }
    }

    if (!strcmp(opcode, "add") && (container_cgroup_path == NULL || container_name == NULL)) {
        perror("add opcode parameter error\n");
        return -1;
    }
 
    if (!strcmp(opcode,"del") && (container_name == NULL)) {
        perror("add opcode parameter error\n");
        return -1;
    }

    if (! strcmp(opcode, "add")){
        err = strncmp(container_cgroup_path, "/cgroups", 8);
        if (err != 0) {
            perror("container pathname is not cgroup dir\n");
            return -1;
        }

        cgroup_id = get_cgroup_id(container_cgroup_path);
        if (cgroup_id < 0) {
            err = cgroup_id;
            printf("fail to get cgroup id \n");
            return err;
        }

        if (! strstr(container_cgroup_path, container_name)){
            perror("container name does  not match cgroup pathname\n");
            return -1;
        }
    }

     ////update config file
       
    if (! strcmp(opcode, "add")){
        char line_data[STRING_LENGTH_MAX];
        FILE *fp = fopen(config_file, "a+");

        if (fp == NULL){
            perror("config file fail to open\n");
            return -1;
        }

        while(fgets(line_data, STRING_LENGTH_MAX, fp) != NULL){
            if (strstr(line_data, container_name)){
                printf("container name:%s exist, not need add operation\n", container_name);
                fclose(fp);
                return 0;
            }
        }

        fprintf(fp, "container_id: %llu, container_name: %s\n", cgroup_id, container_name);
        fclose(fp);
    }
    else if (! strcmp(opcode, "del")){
        char line_data[STRING_LENGTH_MAX];
        FILE *w_fp = NULL, *r_fp = fopen(config_file, "a+");
        bool exist_cgroup = false;

        if (r_fp == NULL) {
            perror("config file fail to open\n");
            return -1;
        } 

        while(fgets(line_data, STRING_LENGTH_MAX, r_fp) != NULL) {
            if (strstr(line_data, container_name)) {
                exist_cgroup = true;
            }
        }

        if (!exist_cgroup) {
            printf("container name:%s not exist, not need del operation\n", container_name);
            fclose(r_fp);
            return 0;
        }

        w_fp = fopen("tmp", "a+");

        if (w_fp == NULL) {
            fclose(r_fp);
            perror("tmp config file fail to open\n");
            return -1;
        }

        while(fgets(line_data, STRING_LENGTH_MAX, r_fp) != NULL){
            if (strstr(line_data, container_name) == NULL){
                fputs(line_data, w_fp);
            }
        }

        fclose(r_fp);
        fclose(w_fp);

        w_fp = fopen(config_file, "w+");

        if (w_fp == NULL){
            perror("config file fail to open\n");
            return -1;
        }

        r_fp = fopen("tmp", "r+");
   
        if (r_fp == NULL){
            fclose(w_fp);
            perror("config file fail to open\n");
            return -1;
        }

        while(fgets(line_data, STRING_LENGTH_MAX, r_fp) != NULL) {
            fputs(line_data, w_fp);
        }

        fclose(r_fp);
        fclose(w_fp);

        ///remove tmp file
        remove("tmp");
    }
    else {
        printf("update config only supports add or del\n");
    }

    return 0;
}
