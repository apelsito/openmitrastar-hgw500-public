// SPDX-License-Identifier: GPL-2.0
/* Kernel-file API used by MuC requests and read-only board telemetry. */

#include <linux/errno.h>
#include <linux/fs.h>
#include <linux/mutex.h>

#define QDRV_COMPAT_MAX_FILES 32

static DEFINE_MUTEX(qdrv_compat_files_lock);
static struct file *qdrv_compat_files[QDRV_COMPAT_MAX_FILES];

static struct file *qdrv_compat_file_get_locked(int handle)
{
	if (handle < 0 || handle >= QDRV_COMPAT_MAX_FILES)
		return NULL;

	return qdrv_compat_files[handle];
}

int qdrv_compat_open(const char *path, int flags, umode_t mode)
{
	struct file *file;
	int handle;

	file = filp_open(path, flags, mode);
	if (IS_ERR(file))
		return PTR_ERR(file);

	mutex_lock(&qdrv_compat_files_lock);
	for (handle = 0; handle < QDRV_COMPAT_MAX_FILES; handle++) {
		if (!qdrv_compat_files[handle]) {
			qdrv_compat_files[handle] = file;
			mutex_unlock(&qdrv_compat_files_lock);
			return handle;
		}
	}
	mutex_unlock(&qdrv_compat_files_lock);

	filp_close(file, NULL);
	return -EMFILE;
}

ssize_t qdrv_compat_read(int handle, void *buffer, size_t count)
{
	struct file *file;
	ssize_t result;

	mutex_lock(&qdrv_compat_files_lock);
	file = qdrv_compat_file_get_locked(handle);
	result = file ? kernel_read(file, buffer, count, &file->f_pos) : -EBADF;
	mutex_unlock(&qdrv_compat_files_lock);

	return result;
}

ssize_t qdrv_compat_write(int handle, const void *buffer, size_t count)
{
	struct file *file;
	ssize_t result;

	mutex_lock(&qdrv_compat_files_lock);
	file = qdrv_compat_file_get_locked(handle);
	result = file ? kernel_write(file, buffer, count, &file->f_pos) : -EBADF;
	mutex_unlock(&qdrv_compat_files_lock);

	return result;
}

int qdrv_compat_close(int handle)
{
	struct file *file;

	mutex_lock(&qdrv_compat_files_lock);
	file = qdrv_compat_file_get_locked(handle);
	if (file)
		qdrv_compat_files[handle] = NULL;
	mutex_unlock(&qdrv_compat_files_lock);

	if (!file)
		return -EBADF;

	return filp_close(file, NULL);
}
