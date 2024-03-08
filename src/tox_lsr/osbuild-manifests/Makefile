NULL=
EMPTY :=
SPACE := $(EMPTY) $(EMPTY)
COMMA := ,
ESCAPEDSPACE := \$(SPACE)
ESCAPEDSPACE_REPLACEMENT := @@SPACE@@

# This is useful to handle space in forech rules
handle-escaped-space = $(subst $(ESCAPEDSPACE),$(ESCAPEDSPACE_REPLACEMENT),$1)
apply-escaped-space = $(subst $(ESCAPEDSPACE_REPLACEMENT),$(SPACE),$1)

HOST_ARCH:=$(shell arch)

ARCHES := x86_64 aarch64


export VM=0

OSBUILD_MPP=osbuild-mpp

DEFINES=
DEFINES_ARGS:=$(foreach def,$(call handle-escaped-space,$(DEFINES)),-D '$(call apply-escaped-space,$(def))')
MPP_ARGS=
export OSBUILD_ARGS=

BUILDDIR=_build
export STOREDIR=$(BUILDDIR)/osbuild_store
export OUTPUTDIR=$(BUILDDIR)/image_output

IMAGEDIR=
DESTDIR=.
EXTRA_DISTRO=
OSBUILDVM_MPP_YML=osbuildvm/osbuildvm.mpp.yml

DISTROS := $(basename $(basename $(notdir f,$(wildcard distro/*.ipp.yml)))) $(if $(EXTRA_DISTRO),$(basename $(basename $(notdir $(EXTRA_DISTRO)))))
MANIFESTS := $(wildcard images/*.mpp.yml) $(foreach DIR,$(IMAGEDIR),$(wildcard $(DIR)/*))

EXTRA_MPP_ARGS= # For internal use
ifdef OSTREE_REPO
EXTRA_MPP_ARGS +=-D ostree_parent_refs='$(shell tools/ot-refs $(OSTREE_REPO))'
endif

export CHECKPOINTS=build
IMAGETYPES := regular ostree
FORMATS := img qcow2 oci.tar repo rootfs ext4 tar aboot
aarch64_TARGETS := ridesx4 rpi4 qdrive3 abootqemu
COMMON_TARGETS := qemu aws
HOST_TARGETS := $(COMMON_TARGETS) $($(HOST_ARCH)_TARGETS)
ALL_TARGETS := $(COMMON_TARGETS) $(foreach a,$(ARCHES), $($(a)_TARGETS))

manifest-get-name = $(basename $(basename $(notdir $1)))
manifest-get-dir = $(notdir $(patsubst %/,%,$(dir $1)))
image-name-noarch = $1-$3-$(call manifest-get-name,$2)-$4
image-name = $(call image-name-noarch,$1,$2,$3,$4).$5

# variable name for image type
regular_IMAGETYPE := regular
ostree_IMAGETYPE := ostree

help:
	@echo
	@echo This makefile is a wrapper around osbuild-mpp and osbuild to easily build images
	@echo
	@echo To build a raw image, run \"make image.img\", or to build a qcow2 image, run \"make image.qcow2\".
	@echo This will build any image from a file called \"image.mpp.yml\" in the \"images\" subdirectory. You can
	@echo pass IMAGEDIR=/some/other/path to make also to pick up manifests from an external directory.
	@echo
	@echo For example, to build a minimal qcow2 image with ostree support targeting qemu, run:
	@echo '  make cs9-qemu-minimal-ostree.$(HOST_ARCH).qcow2'
	@echo
	@echo Other extensions are also supported:
	@echo \ \* .repo: Generate a repo with an ostree commit \(only works for ostree targets\)
	@echo \ \* .rootfs: Generate a directory with the rootfs content
	@echo \ \* .tar: Generate a tar file with the rootfs content
	@echo \ \* .ext4: Generate an ext4 filesystem with the rootfs content  \(size from \"image_size\"\)
	@echo \ \* .oci.tar: Generate an oci container image with the rootfs content
	@echo \ \* .aboot: Generate an ext4 root filesystem and an android boot image \(for aboot targets\)
	@echo
	@echo You can pass variable declarations to osbuild-mpp with the DEFINES make variable.
	@echo Multiple defines are separated by space, if you need a space inside a value escape it using \"\\ \".
	@echo For example, to add extra rpms to a minimal regular image, use:
	@echo "  make cs9-qemu-minimal-regular.$(HOST_ARCH).qcow2 DEFINES='extra_rpms=[\"gdb\",\"strace\"]'"
	@echo
	@echo To easily run the image with qemu, you can use the included runvm tool, like:
	@echo \ \ ./runvm cs9-qemu-minimal-regular.$(HOST_ARCH).qcow2
	@echo
	@echo There are some additional targets:
	@echo  \ \ manifests: generates resolved json manifests for all images without building them.
	@echo  \ \ clean_caches: Removes intermediate image build artifacts \(that improve rebuild speed\)
	@echo  \ \ clean_downloads: Removes files downloaded during image builds
	@echo  \ \ clean: Run clean_caches and clean_downloads
	@echo  \ \ osbuildvm-images: Build a image that can be used to build images inside a VM
	@echo
	@echo There are also some common conversion rules:
	@echo  \ \ foo.aboot.simg will build aboot.img / rootfs.img and convert rootfs.img using img2simg
	@echo  \ \ foo.ext4.simg will build foo.ext4 and then convert it with img2simg
	@echo  \ \ foo.simg will build foo.img and then convert it with img2simg
	@echo  \ \ foo.tar.gz will build $foo.tar and then gzip it
	@echo
	@echo "When building a custom variant of an image (say with an extra package) you can use a"
	@echo custom @suffix to change the name of the produced file. For example:
	@echo "  make cs9-qemu-minimal-ostree@gdb.$(HOST_ARCH).qcow2 DEFINES='extra_rpms=[\"gdb\"]'"
	@echo
	@echo If you pass VM=1, then the images used from \"make osbuildvm-images\" will be used to do the
	@echo actual building. This means that you don\'t need sudo rights to run osbuild, and it means
	@echo architectures other than the current ones can be built.
	@echo
	@echo Available image targets can be listed with \"make list-targets\"
	@echo

list-targets:
	@echo Available image targets \(for $(HOST_ARCH)\) are:
	@echo
	@$(foreach d, $(DISTROS), $(foreach m, $(MANIFESTS), $(foreach t, $(HOST_TARGETS), $(foreach i,$(IMAGETYPES), echo -e "   "  $(call image-name,$d,$m,$t,$i,$(HOST_ARCH)).[$(subst $(SPACE),$(COMMA),$(FORMATS))];))))
	@echo

# We pre-create all the toplevel dirs, so that they are owned by the user, not root (when created under sudo)
.PHONY: $(BUILDDIR)
$(BUILDDIR):
	@mkdir -p $(BUILDDIR)
	@mkdir -p $(STOREDIR)/{objects,refs,sources/org.osbuild.files,tmp}
	@mkdir -p $(OUTPUTDIR)

# Template rule for producing osbuild json manifest from mpp yaml and image type
# $1 == distro name
# $2 == yaml manifest path
# $3 == Target name
# $4 == Image type
# $5 == Arch
define json-rule
$(BUILDDIR)/$(call image-name,$1,$2,$3,$4,$5).json: $2 $(BUILDDIR)
	$(OSBUILD_MPP) -D $(if $(EXTRA_DISTRO),distro_dir="\"$(dir $(EXTRA_DISTRO))\"",distro_dir="\"distro\"") -I . -D image_type="\"$($4_IMAGETYPE)\"" -D arch=\"$5\" -D distro_name="\"$1\"" -D target="\"$3\"" $(DEFINES_ARGS) $(EXTRA_MPP_ARGS) $(MPP_ARGS) $$< $$@
.PHONY: $(BUILDDIR)/$(call image-name,$1,$2,$3,$4,$5).json
endef

$(foreach d, $(DISTROS), \
 $(foreach m, $(MANIFESTS), \
  $(foreach a,$(ARCHES), \
   $(foreach t,$(COMMON_TARGETS) $($(a)_TARGETS), \
    $(foreach i,$(IMAGETYPES), \
     $(eval $(call json-rule,$d,$m,$t,$i,$a)))))))

# Template rule for producing image from json manifest
# $1 == distro name
# $2 == Manifest path
# $3 == Target
# $4 == Image type
# $5 == Arch
# $6 == Export format (extension)
define image-rule
$(call image-name,$1,$2,$3,$4,$5).$6: $(BUILDDIR)/$(call image-name,$1,$2,$3,$4,$5).json
	@tools/runosbuild $(DESTDIR)/"$$@" "$$<" "$3" "$4" "$5" "$6"

$(call image-name-noarch,$1,$2,$3,$4)@%.$5.$6: $(BUILDDIR)/$(call image-name,$1,$2,$3,$4,$5).json
	@tools/runosbuild $(DESTDIR)/"$$@" "$$<" "$3" "$4" "$5" "$6"
endef

$(foreach d, $(DISTROS), \
 $(foreach m, $(MANIFESTS), \
  $(foreach a,$(ARCHES), \
   $(foreach t, $(COMMON_TARGETS) $($(a)_TARGETS), \
    $(foreach f,$(FORMATS), \
     $(foreach i,$(IMAGETYPES), \
      $(eval $(call image-rule,$d,$m,$t,$i,$a,$f))))))))

# Rule to pre-generate all manifests
manifests: $(foreach d, $(DISTROS),$(foreach m, $(MANIFESTS), $(foreach a,$(ARCHES), $(foreach t, $(COMMON_TARGETS) $($(a)_TARGETS), $(foreach i,$(IMAGETYPES), $(BUILDDIR)/$(call image-name,$d,$m,$t,$i,$a).json)))))

define packages-rule
.PHONY: packages-$(call manifest-get-name,$1).json
packages-$(call manifest-get-name,$1).json: $1
	osbuild-mpp $$< -D arch=\"x86_64\" - | jq -f tools/extract-rpms.jq > $$@.x86_64
	osbuild-mpp $$< -D arch=\"aarch64\" - | jq -f tools/extract-rpms.jq > $$@.aarch64
	echo 1 | jq --indent 4 -f tools/create-packagelist.jq --slurpfile x86_64 $$@.x86_64 --slurpfile aarch64 $$@.aarch64 > $$@
endef

$(foreach m, $(MANIFESTS), $(eval $(call packages-rule,$m)))

.PHONY: clean_downloads
clean_downloads:
	sudo rm -rf $(BUILDDIR)/osbuild_store/sources/org.osbuild.files/*

.PHONY: clean_caches
clean_caches:
	sudo rm -rf $(STOREDIR)/refs/*
	sudo rm -rf $(STOREDIR)/refs_tars/*
	sudo rm -rf $(STOREDIR)/objects/*
	sudo rm -rf $(STOREDIR)/tmp/*
	sudo rm -rf $(STOREDIR)/image_output/*

.PHONY: clean
clean: clean_downloads clean_caches

ifeq ($(VM), 1)
VM_SUDO=
VM_OSBUILD="osbuildvm/osbuildvm --image-dir=$(BUILDDIR) --arch=$(HOST_ARCH)"
else
VM_SUDO=sudo
VM_OSBUILD=sudo osbuild
endif

.PHONY: osbuildvm-images
osbuildvm-images: $(BUILDDIR)
	$(OSBUILD_MPP) $(OSBUILDVM_MPP_YML) $(BUILDDIR)/osbuildvm-$(HOST_ARCH).json
	$(VM_OSBUILD) --store $(STOREDIR) --output-directory $(OUTPUTDIR) --export osbuildvm $(BUILDDIR)/osbuildvm-$(HOST_ARCH).json
	cp $(OUTPUTDIR)/osbuildvm/disk.qcow2 $(BUILDDIR)/osbuildvm-$(HOST_ARCH).img
	cp $(OUTPUTDIR)/osbuildvm/initramfs $(BUILDDIR)/osbuildvm-$(HOST_ARCH).initramfs
	cp $(OUTPUTDIR)/osbuildvm/vmlinuz $(BUILDDIR)/osbuildvm-$(HOST_ARCH).vmlinuz
	$(VM_SUDO) rm -rf $(OUTPUTDIR)/osbuildvm

%.aboot.simg : %.aboot
	img2simg $</rootfs.img $</rootfs.simg
	rm $</rootfs.img

%.ext4.simg : %.ext4
	img2simg $< $@
	rm $<

%.simg : %.img
	img2simg $< $@
	rm $<

%.tar.gz : %.tar
	gzip -f $<

AUTOSIGREPO=https://mirror.stream.centos.org/SIGs/9-stream/automotive
define u-boot-rule
qemu-u-boot-$1.bin:
	DLDIR=`mktemp -d` && \
	dnf download -q --downloaddir $$$$DLDIR --disablerepo "*" --repofrompath "autosig,${AUTOSIGREPO}/$1/packages-main/" autosig-u-boot && \
	rpm2cpio $$$$DLDIR/autosig-u-boot-*.rpm | cpio -id -D $$$$DLDIR && \
	mv $$$$DLDIR/boot/u-boot.bin $$@ && \
	rm -rf $$$$DLDIR
endef
$(foreach a,$(ARCHES), $(eval $(call u-boot-rule,$a)))
