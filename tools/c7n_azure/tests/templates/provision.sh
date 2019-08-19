#!/bin/bash
IFS=$'\n\t'

# IFS new value is less likely to cause confusing bugs when looping arrays or arguments (e.g. $@)

# If `az ad signed-in-user show` fails then update your Azure CLI version

resourceLocation="South Central US"
templateDirectory="$( cd "$( dirname "$0" )" && pwd )"

deploy_resource() {
  rgName="test_$filenameNoExtension"

  az group create --name $rgName --location $resourceLocation

  if [[ "$1" =~ "keyvault.json" ]]; then
    azureAdUserObjectId=$(az ad signed-in-user show --query objectId  --output tsv)

    az group deployment create --resource-group $rgName --template-file $file \
        --parameters "userObjectId=$azureAdUserObjectId"

    vault_name=$(az keyvault list --resource-group $rgName --query [0].name --output tsv)
    az keyvault key create --vault-name $vault_name --name cctestrsa --kty RSA
    az keyvault key create --vault-name $vault_name --name cctestec --kty EC
  elif [[ "$1" =~ "aks.json" ]]; then
    az group deployment create --resource-group $rgName --template-file $file --parameters client_id=$AZURE_CLIENT_ID client_secret=$AZURE_CLIENT_SECRET --mode Complete
  else
    az group deployment create --resource-group $rgName --template-file $file --mode Complete
  fi

}

# Create resource groups and deploy for each template file
for file in "$templateDirectory"/*.json; do
  fileName=${file##*/}
  filenameNoExtension=${fileName%.*}

  if [ $# -eq 0 ] || [[ "$@" == "$filenameNoExtension" ]]; then
    deploy_resource ${file}
  else
    echo "Skipping ${filenameNoExtension}"
  fi
done

# Deploy ACS resource
rgName=test_containerservice
if [ $# -eq 0 ] || [[ "$@" =~ "containerservice" ]]; then
  az group create --name $rgName --location $resourceLocation
  az acs create -n cctestacs -d cctestacsdns -g $rgName --generate-ssh-keys --orchestrator-type kubernetes
else
  echo "Skipping $rgName"
fi
#
## Deploy Azure Policy Assignment
#if [ $# -eq 0 ] || [[ "$@" =~ "policyassignment" ]]; then
#  # 06a78e20-9358-41c9-923c-fb736d382a4d is an id for 'Audit VMs that do not use managed disks' policy
#  az policy assignment create --display-name cctestpolicy --name cctestpolicy --policy '06a78e20-9358-41c9-923c-fb736d382a4d'
#else
#  echo "Skipping policyassignment"
#fi

