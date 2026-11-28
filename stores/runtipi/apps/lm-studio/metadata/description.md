# Lm-studio

![Lm-studio](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/lmstudio-logo.png)

[LM Studio](https://lmstudio.ai/) can run local AI models like gpt-oss, Llama, Gemma, Qwen, and DeepSeek privately on your computer.

## Application setup

LM Studio can be accessed at:

* https://yourhost:3001/

### GPU Support

This image is Arch based and supports the following GPUs:

* Cuda v13- This requires a 2000 series or higher Nvidia video card running the latest binary drivers, v12 is not supported.
* Vulkan- This requires a semi modern AMD GPU.

ROCm is not supported at this time due to it's size and Vulkan option for AMD.

#### Minimum run commands (start here then expand to fit your needs)

AMD GPUs:

```bash
docker run --rm -it \
  --shm-size=1gb \
  --device /dev/dri \
  -e AUTO_GPU=true \
  -p 3001:3001 \
  linuxserver/lm-studio bash
```

Nvidia GPUs:

As of driver `595.80` with NVIDIA Container Toolkit installed:

```bash
# Host level modprobe modeset
nvidia-modprobe --modeset
```

```bash
docker run --rm -it \
  --shm-size=1gb \
  --device /dev/nvidia-modeset \
  --runtime nvidia \
  --gpus all \
  -e AUTO_GPU=true \
  -p 3001:3001 \
  linuxserver/lm-studio bash
```

### AI tools included in this image

This image comes preloaded with a set of AI development and automation tools centered around LM Studio, enabling local model execution, and integration inside a KDE desktop environment.

At the core is LM Studio along with its developer ecosystem via lmstudio SDK, providing programmatic access to local models and workflows.

For AI-assisted coding and agentic workflows, the image includes:

* Aider (via `aider-install`) for git-aware code editing with LLM assistance (manual configuration required)
* Cline for agent style development inside development environments
* Code-OSS for a desktop IDE with AI plugin support
* OpenClaw for running autonomous AI agents that execute tasks through workflows and messaging based interaction
* OpenCode AI for code generation and refactoring

These tools are primarily **CLI and developer focused**, and are designed to be configured by the user from the terminal on first launch to connect to a local LM Studio backend.

Included is a desktop launcher for LLMster to provide the backend for these tools in the desktop environment in a headless manner. This can also be launched with `lms server start` from the command line or from the desktop application via the taskbar icon.

**Important notes:**

* LM Studio (the desktop application) and LLMster cannot be run at the same time, as they both manage overlapping runtime resources for local model access and will conflict if launched concurrently.
* All included AI tools require initial configuration to point to the active LM Studio backend before use.

Image: `ghcr.io/linuxserver-playground/lm-studio:latest` ([https://github.com/linuxserver-playground/docker-lm-studio](https://github.com/linuxserver-playground/docker-lm-studio))
