// SPDX-License-Identifier: GPL-2.0
/* HGW-500BNA-QCv2 RAM-only, read-only physical NOR window exporter. */
#include <linux/fs.h>
#include <linux/io.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/slab.h>
#include <linux/uaccess.h>

#define OMSPIRO_PHYS_BASE 0x90000000UL
#define OMSPIRO_SIZE      0x01000000UL
#define OMSPIRO_NAME      "omspiro"

static void __iomem *omspiro_base;
static atomic_t omspiro_first_read = ATOMIC_INIT(0);

static int omspiro_open(struct inode *inode, struct file *file)
{
	(void)inode;
	if (file->f_mode & FMODE_WRITE)
		return -EPERM;
	return 0;
}

static ssize_t omspiro_read(struct file *file, char __user *user,
		size_t count, loff_t *position)
{
	u8 *bounce;
	ssize_t copied = 0;
	loff_t pos;

	if (!position || *position < 0)
		return -EINVAL;
	pos = *position;
	if (pos >= OMSPIRO_SIZE || !count)
		return 0;
	if (count > OMSPIRO_SIZE - pos)
		count = OMSPIRO_SIZE - pos;

	bounce = kmalloc(PAGE_SIZE, GFP_KERNEL);
	if (!bounce)
		return -ENOMEM;

	if (atomic_cmpxchg(&omspiro_first_read, 0, 1) == 0)
		pr_info("OMSPIRO first-read offset=0x%llx count=%zu\n",
			(unsigned long long)pos, count);

	while (count) {
		size_t step = min_t(size_t, count, PAGE_SIZE);

		memcpy_fromio(bounce, omspiro_base + pos, step);
		if (copy_to_user(user + copied, bounce, step)) {
			copied = copied ? copied : -EFAULT;
			break;
		}
		pos += step;
		copied += step;
		count -= step;
	}
	kfree(bounce);
	if (copied > 0)
		*position = pos;
	return copied;
}

static loff_t omspiro_llseek(struct file *file, loff_t offset, int whence)
{
	return fixed_size_llseek(file, offset, whence, OMSPIRO_SIZE);
}

static const struct file_operations omspiro_fops = {
	.owner = THIS_MODULE,
	.open = omspiro_open,
	.read = omspiro_read,
	.llseek = omspiro_llseek,
};

static struct miscdevice omspiro_device = {
	.minor = MISC_DYNAMIC_MINOR,
	.name = OMSPIRO_NAME,
	.fops = &omspiro_fops,
	.mode = 0400,
};

static int __init omspiro_init(void)
{
	int ret;

	if (!of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")) {
		pr_err("OMSPIRO refused incompatible-machine\n");
		return -ENODEV;
	}
	omspiro_base = ioremap(OMSPIRO_PHYS_BASE, OMSPIRO_SIZE);
	if (!omspiro_base) {
		pr_err("OMSPIRO ioremap-failed phys=0x%08lx size=0x%08lx\n",
			OMSPIRO_PHYS_BASE, OMSPIRO_SIZE);
		return -ENOMEM;
	}
	ret = misc_register(&omspiro_device);
	if (ret) {
		iounmap(omspiro_base);
		omspiro_base = NULL;
		return ret;
	}
	pr_info("OMSPIRO ready phys=0x%08lx size=0x%08lx dev=/dev/%s read-only\n",
		OMSPIRO_PHYS_BASE, OMSPIRO_SIZE, OMSPIRO_NAME);
	return 0;
}

static void __exit omspiro_exit(void)
{
	misc_deregister(&omspiro_device);
	if (omspiro_base)
		iounmap(omspiro_base);
	omspiro_base = NULL;
	pr_info("OMSPIRO stopped\n");
}

module_init(omspiro_init);
module_exit(omspiro_exit);
MODULE_DESCRIPTION("OpenMitraStar HGW-500BNA-QCv2 physical NOR read-only exporter");
MODULE_AUTHOR("OpenMitraStar");
MODULE_LICENSE("GPL");
