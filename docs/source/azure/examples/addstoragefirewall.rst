Add storage firewall
====================

.. code-block:: yaml

    policies:
        - name: add-storage-firewall
        description: |
            find storage accounts without open ip list and restrict them
        resource: azure.storage
        
        filters:
        - type: value
          key: properties.networkAcls.ipRules
          value_type: size
          op: eq
          value: 0

        actions:
        - type: set-network-rules
          default-action: Deny
          bypass: Logging, Metrics
          ip-rules:
              - ip-address-or-range: 11.12.13.14
              - ip-address-or-range: 21.22.23.24
          virtual-network-rules:
              - virtual-network-resource-id: /subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworks/vnet1/subnets/subnet1
              - virtual-network-resource-id: /subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworks/vnet2/subnets/subnet2
