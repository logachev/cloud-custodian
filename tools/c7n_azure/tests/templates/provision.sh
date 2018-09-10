#!/bin/bash
IFS=$'\n\t'


# IFS new value is less likely to cause confusing bugs when looping arrays or arguments (e.g. $@)

resourceLocation="South Central US"
templateDirectory="$( cd "$( dirname "$0" )" && pwd )"

# Create resource groups and deploy for each template file
for file in "$templateDirectory"/*.json; do
  fileName=${file##*/}
  filenameNoExtension=${fileName%.*}
  rgName="test_$filenameNoExtension"

  if [ $# -eq 0 ] || [[ "$@" =~ "$filenameNoExtension" ]]; then
      az group create --name $rgName --location $resourceLocation
      az group deployment create --resource-group $rgName --template-file $file
  else
    echo "Skipping $rgName"
  fi
done

# Deploy ACS resource
rgName=test_containerservice
az group create --name $rgName --location $resourceLocation
az acs create -n cctestacs -d cctestacsdns -g $rgName --generate-ssh-keys --orchestrator-type kubernetes
