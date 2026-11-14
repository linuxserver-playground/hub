# Foldingathome

![Foldingathome](https://foldingathome.org/wp-content/uploads/2016/09/folding-at-home-logo.png)

[Folding@home](https://foldingathome.org/) is a distributed computing project for simulating protein dynamics, including the process of protein folding and the movements of proteins implicated in a variety of diseases. It brings together citizen scientists who volunteer to run simulations of protein dynamics on their personal computers. Insights from this data are helping scientists to better understand biology, and providing new opportunities for developing therapeutics.

## Application setup

This image sets up the Folding@home client. The interface is available at [https://app.foldingathome.org](https://app.foldingathome.org).

Before setting up this container, please register for an account on [https://app.foldingathome.org](https://app.foldingathome.org) and retrieve the account token shown in the account settings. That value should be populated in the `ACCOUNT_TOKEN` env var.

Once the container is created with the token and the machine name, the instance should be listed in the web app and can be controlled there.

Afterwards, the `ACCOUNT_TOKEN` and the `MACHINE_NAME` vars can be removed as the instance will already be associated with the online account and the info stored in the config folder.

## Migration from version 7.6

Version 8 of fah-client has been rewritten and has some breaking changes that we can't automatically mitigate in this container.

Unlike v7, v8 no longer bundles a local webgui. The web app is loaded from an online source and can only auto-detect instances that are running on the same machine (bare metal) as the browser. This is not possible in a docker container. Therefore, upgrading to v8 requires registering for an online account, retrieving the account token and setting it in the new env var `ACCOUNT_TOKEN`, along with a friendly name in `MACHINE_NAME`.

## GPU Hardware Acceleration

### Nvidia

Hardware acceleration users for Nvidia will need to install the container runtime provided by Nvidia on their host, instructions can be found here:
https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
We automatically add the necessary environment variable that will utilise all the features available on a GPU on the host. Once nvidia container toolkit is installed on your host you will need to re/create the docker container with the nvidia container runtime `--runtime=nvidia` and add an environment variable `-e NVIDIA_VISIBLE_DEVICES=all` (can also be set to a specific gpu's UUID, this can be discovered by running `nvidia-smi --query-gpu=gpu_name,gpu_uuid --format=csv` ). NVIDIA automatically mounts the GPU and drivers from your host into the foldingathome docker container.

Image: `ghcr.io/linuxserver-playground/foldingathome:latest` ([https://github.com/linuxserver-playground/docker-foldingathome](https://github.com/linuxserver-playground/docker-foldingathome))
