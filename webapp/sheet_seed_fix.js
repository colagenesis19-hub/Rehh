// Keep the workflow form aligned with Google Sheet data returned by /api/my-open-orders.
// Fields already present in Sheet must not be asked again.
workflowSeed = function(order){
  const present = v => {
    const text = String(v ?? '').trim();
    return ['', '-', 'N/A', 'NA', 'NONE', '#N/A'].includes(text.toUpperCase()) ? '' : text;
  };
  return {
    ticket_id: order.ticket_id === 'MANUAL' ? '' : present(order.ticket_id),
    service_number: present(order.service_number),
    customer_name: present(order.customer_name),
    address: present(order.address),
    customer_phone: present(order.customer_phone),
    voip_number: present(order.voip_number),
    old_sn: present(order.old_sn),
    new_sn: present(order.new_sn),
    ont_type: present(order.ont_type),
    sto: present(order.sto) || present(state.myOpenOrders?.technician?.sto),
    valins_id: present(order.valins_id),
    result: present(order.result),
    config_description: present(order.config_description),
    report_description: present(order.report_description)
  };
};
