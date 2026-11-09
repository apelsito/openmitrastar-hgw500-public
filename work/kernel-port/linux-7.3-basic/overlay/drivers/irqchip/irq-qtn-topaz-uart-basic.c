// SPDX-License-Identifier: GPL-2.0-only
/* Source-only Linux 7.3 Topaz BASIC UART0 demultiplexer.
 * Core parent hwirq24; child hwirq16. No GPIO/timer/misc support.
 * RESET_CAUSE is read for UART pending; LHOST_ORINT_EN owns UART bits only.
 */
#include <linux/bitops.h>
#include <linux/errno.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/irq.h>
#include <linux/irqchip.h>
#include <linux/irqchip/chained_irq.h>
#include <linux/irqdesc.h>
#include <linux/irqdomain.h>
#include <linux/of_address.h>
#include <linux/of_irq.h>
#include <linux/slab.h>
#include <linux/spinlock.h>

#define TOPAZ_BASIC_SYSCTL 0xe0000000
#define TOPAZ_BASIC_SYSCTL_BYTES 0x5c
#define TOPAZ_RESET_CAUSE 0x10
#define TOPAZ_LHOST_ORINT_EN 0x58
#define TOPAZ_UART_PARENT_HWIRQ 24
#define TOPAZ_UART0_HWIRQ 16
#define TOPAZ_UART_CHILD_MASK GENMASK(17, 16)

struct topaz_uart_irqc {
    void __iomem *sysctl;
    struct irq_domain *domain;
    raw_spinlock_t lock;
};

static void topaz_uart_mask(struct irq_data *data)
{
    struct topaz_uart_irqc *irqc = irq_data_get_irq_chip_data(data);
    unsigned long flags;
    u32 enabled;

    raw_spin_lock_irqsave(&irqc->lock, flags);
    enabled = readl(irqc->sysctl + TOPAZ_LHOST_ORINT_EN);
    writel(enabled & ~BIT(TOPAZ_UART0_HWIRQ),
           irqc->sysctl + TOPAZ_LHOST_ORINT_EN);
    raw_spin_unlock_irqrestore(&irqc->lock, flags);
}

static void topaz_uart_unmask(struct irq_data *data)
{
    struct topaz_uart_irqc *irqc = irq_data_get_irq_chip_data(data);
    unsigned long flags;
    u32 enabled;

    raw_spin_lock_irqsave(&irqc->lock, flags);
    enabled = readl(irqc->sysctl + TOPAZ_LHOST_ORINT_EN);
    writel(enabled | BIT(TOPAZ_UART0_HWIRQ),
           irqc->sysctl + TOPAZ_LHOST_ORINT_EN);
    raw_spin_unlock_irqrestore(&irqc->lock, flags);
}

static int topaz_uart_set_type(struct irq_data *data, unsigned int type)
{
    return type == IRQ_TYPE_NONE || type == IRQ_TYPE_LEVEL_HIGH ? 0 : -EINVAL;
}

static struct irq_chip topaz_uart_chip = {
    .name = "topaz-basic-uart0",
    .irq_mask = topaz_uart_mask,
    .irq_unmask = topaz_uart_unmask,
    .irq_set_type = topaz_uart_set_type,
};

static int topaz_uart_map(struct irq_domain *domain, unsigned int virq,
                          irq_hw_number_t hwirq)
{
    if (hwirq != TOPAZ_UART0_HWIRQ)
        return -EINVAL;
    irq_set_chip_data(virq, domain->host_data);
    irq_set_chip_and_handler(virq, &topaz_uart_chip, handle_level_irq);
    irq_set_noprobe(virq);
    return 0;
}

static const struct irq_domain_ops topaz_uart_domain_ops = {
    .map = topaz_uart_map,
    .xlate = irq_domain_xlate_twocell,
};

static void topaz_uart_dispatch(struct irq_desc *desc)
{
    struct topaz_uart_irqc *irqc = irq_desc_get_handler_data(desc);
    struct irq_chip *parent_chip = irq_desc_get_chip(desc);
    unsigned long flags;
    u32 cause, enabled;

    chained_irq_enter(parent_chip, desc);
    raw_spin_lock_irqsave(&irqc->lock, flags);
    cause = readl(irqc->sysctl + TOPAZ_RESET_CAUSE);
    enabled = readl(irqc->sysctl + TOPAZ_LHOST_ORINT_EN);
    raw_spin_unlock_irqrestore(&irqc->lock, flags);
    /* One bounded snapshot; never spin while waiting for UART hardware. */
    if ((cause & BIT(7)) && (enabled & BIT(TOPAZ_UART0_HWIRQ)))
        generic_handle_domain_irq(irqc->domain, TOPAZ_UART0_HWIRQ);
    chained_irq_exit(parent_chip, desc);
}

static int __init topaz_uart_init(struct device_node *node,
                                 struct device_node *parent)
{
    struct topaz_uart_irqc *irqc;
    struct resource resource, extra;
    struct irq_data *parent_data;
    unsigned int parent_irq;
    u32 enabled;
    int ret = -ENODEV;

    if (!parent || !of_machine_is_compatible("openmitrastar,hgw500-topaz-basic") ||
        of_irq_count(node) != 1 ||
        of_address_to_resource(node, 0, &resource) ||
        !of_address_to_resource(node, 1, &extra) ||
        resource.start != TOPAZ_BASIC_SYSCTL ||
        resource_size(&resource) != TOPAZ_BASIC_SYSCTL_BYTES)
        return -EINVAL;
    parent_irq = irq_of_parse_and_map(node, 0);
    parent_data = irq_get_irq_data(parent_irq);
    /* Compare hardware number, never assume the Linux virtual IRQ number. */
    if (!parent_irq || !parent_data || parent_data->hwirq != TOPAZ_UART_PARENT_HWIRQ)
        return -EINVAL;
    irqc = kzalloc(sizeof(*irqc), GFP_KERNEL);
    if (!irqc)
        return -ENOMEM;
    irqc->sysctl = of_iomap(node, 0);
    if (!irqc->sysctl)
        goto err_free;
    raw_spin_lock_init(&irqc->lock);
    irqc->domain = irq_domain_create_linear(of_fwnode_handle(node), 32,
                                            &topaz_uart_domain_ops, irqc);
    if (!irqc->domain)
        goto err_unmap;
    /* Keep every non-UART child unchanged. UART1 stays masked: no handler. */
    enabled = readl(irqc->sysctl + TOPAZ_LHOST_ORINT_EN);
    writel(enabled & ~TOPAZ_UART_CHILD_MASK,
           irqc->sysctl + TOPAZ_LHOST_ORINT_EN);
    irq_set_chained_handler_and_data(parent_irq, topaz_uart_dispatch, irqc);
    pr_info("Topaz BASIC UART0 IRQ: parent hwirq24 / virq%u, child hwirq16\n",
            parent_irq);
    return 0;

err_unmap:
    iounmap(irqc->sysctl);
err_free:
    kfree(irqc);
    return ret;
}

IRQCHIP_DECLARE(topaz_basic_uart0, "openmitrastar,topaz-uart0-irqc",
                 topaz_uart_init);
