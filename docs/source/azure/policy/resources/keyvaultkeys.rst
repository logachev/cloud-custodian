.. _azure_keyvaultkeys:

Key Vault Keys
==============

Filters
-------
- Standard Value Filter (see :ref:`filters`)
    - Model: `Key Vault Key <https://docs.microsoft.com/en-us/python/api/azure-keyvault/azure.keyvault.v7_0.models.keyitem?view=azure-python>`_

- `keyvault` filter: filters keys from specified list of keyvaults.
    - `keyvault`: array of strings, allowed keyvault names

- `key-type` filter: Find all keys with specified types
    - `key-types`: array of types. 
        - Possible values: `RSA`, `RSA-HSM`, `EC`, `EC-HSM` 
    

Example Policies
----------------

This policy will find all Keys in `keyvault_test` and `keyvault_prod` KeyVaults

 .. code-block:: yaml
     policies:
       - name: keyvault-keys
         description:
           List all keys that are older than 30 days
         resource: azure.keyvault-keys
         filters:
           - type: keyvault
             keyvaults:
               - keyvault_test
               - keyvault_prod


This policy will find all Keys in all KeyVaults that are older than 30 days

 .. code-block:: yaml
     policies:
       - name: keyvault-keys
         description:
           List all keys that are older than 30 days
         resource: azure.keyvault-keys
         filters:
           - type: value
             key: attributes.created
             value_type: age
             op: gt
             value: 1


This policy will find all Keys in all KeyVaults that are not RSA-HSM

 .. code-block:: yaml
     policies:
       - name: keyvault-keys
         description:
           List all non-RSA-HSM keys
         resource: azure.keyvault-keys
         filters:
           - not:
              - type: key-type
                key-types:
                  - RSA-HSM
