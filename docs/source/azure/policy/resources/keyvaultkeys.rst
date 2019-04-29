.. _azure_keyvaultkeys:

Key Vault Keys
==============

Filters
-------
- Standard Value Filter (see :ref:`filters`)
    - Model: `Key Vault Key <https://docs.microsoft.com/en-us/python/api/azure-keyvault/azure.keyvault.v7_0.models.keyitem?view=azure-python>`_

- Key Type Filter: Find all keys with specified types
    - `key-types`: array of types. 
        - Possible values: `RSA`, `RSA-HSM`, `EC`, `EC-HSM` 
    

Example Policies
----------------

This policy will find all Keys in all KeyVaults that are older than 30 days

 .. code-block:: yaml
     policies:
        - name: keyvault-keys
          description:
            List all keys that are older than 30 days
          resource: azure.keyvault-key
          filters:
            - type: value
              key: created
              value_type: age
              op: gt
              value: 30


This policy will find all Keys in all KeyVaults that are not RSA-HSM

 .. code-block:: yaml
     policies:
        - name: keyvault-keys
          description:
            List all non-RSA-HSM keys
          resource: azure.keyvault-key
          filters:
            - type: not
               - type: key-type
                  key-types:
                    - RSA-HSM