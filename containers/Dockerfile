FROM quay.io/centos/centos:centos7

RUN sed -i '/^mirror/d;s,#\(baseurl=http://\)mirror,\1vault,' /etc/yum.repos.d/*.repo && \
    yum update -y && PKGS="centos-release-ansible-29" && \
    yum install -y $PKGS && rpm -V $PKGS && \
    sed -i '/^mirror/d;s,#\(baseurl=http://\)mirror,\1vault,' /etc/yum.repos.d/*.repo && \
    PKGS="ansible openssh-clients" && \
    yum -y install $PKGS && rpm -V $PKGS && yum clean all

ENTRYPOINT ["/usr/bin/ansible-playbook"]
