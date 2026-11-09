// SPDX-License-Identifier: GPL-2.0-only
#include <stddef.h>
#include <qtn/shared_params.h>

char om_size_shared_params[sizeof(shared_params) + 1];
char om_off_vdev_lhost[offsetof(shared_params, vdev_lhost) + 1];
char om_off_vdev_bus[offsetof(shared_params, vdev_bus) + 1];
char om_off_vport_lhost[offsetof(shared_params, vport_lhost) + 1];
char om_off_vport_bus[offsetof(shared_params, vport_bus) + 1];
char om_off_vlan_info[offsetof(shared_params, vlan_info) + 1];
