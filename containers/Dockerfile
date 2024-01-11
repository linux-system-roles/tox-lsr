FROM quay.io/centos/centos:centos7

RUN yum update -y && PKGS="centos-release-ansible-29" && \
    yum install -y $PKGS && rpm -V $PKGS && \
    PKGS="ansible openssh-clients" && \
    yum -y install $PKGS && rpm -V $PKGS && \
    yum clean all

ENTRYPOINT ["/usr/bin/ansible-playbook"]
