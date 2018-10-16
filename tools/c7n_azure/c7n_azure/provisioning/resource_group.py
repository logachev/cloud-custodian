from c7n_azure.provisioning.deployment_unit import DeploymentUnit

class ResourceGroupUnit(DeploymentUnit):

    def __init__(self):
        super().__init__()
        self.client = self.session.client('azure.mgmt.resource.ResourceManagementClient')
        self.type = "Resource Group"

    def verify_params(self, params):
        return set(params.keys()) == set({'name', 'location'})

    # Override get() function to minimize logs
    def get(self, params):
        try:
            return self.client.resource_groups.get(params['name'])
        except:
            return None

    def _provision(self, params):
        return self.client.resource_groups.create_or_update(params['name'],
                      {'location': params['location']})
