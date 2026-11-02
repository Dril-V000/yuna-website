# How to Install Ollama on Windows 11: Complete Setup Guide (2026)

Running large language models locally has shifted from an experimental hobby to a standard part of the modern developer workflow. Whether you want to test prompt engineering offline, integrate AI into a local application without paying per-token API costs, or keep sensitive data on your own hardware, Ollama provides one of the cleanest runtimes for this task. 

This guide walks you through the technical process to install ollama windows 11, configure your environment, and run your first local model using the command line and an API client.

## System Requirements and Prerequisites

Before downloading any binaries, you need to ensure your Windows 11 machine meets the hardware and software prerequisites for running large language models efficiently. While Ollama can run on a CPU, inference speeds will be slow unless you have a dedicated graphics card with adequate Video RAM (VRAM).

For an optimal experience, your system should meet the following specifications:
- Operating System: Windows 11 (64-bit), updated to the latest build with WSL 2 support enabled if you plan on advanced containerized workflows, though the native Windows installer operates independently.
- Processor: Modern multi-core CPU (Intel Core i5/i7/i9 12th gen or newer, or AMD Ryzen 5/7/9 5000 series or newer).
- Memory (RAM): Minimum 16GB RAM for running 7B and 8B parameter models. 32GB RAM is recommended if you intend to run larger 13B or 34B models comfortably alongside your regular desktop applications.
- Graphics (GPU): NVIDIA GPU with Compute Capability 6.1 or higher (GTX 10-series or newer, RTX series preferred) with the latest CUDA drivers installed, or an AMD GPU with ROCm support where applicable.

Make sure your graphics drivers are up to date before proceeding. If you have an NVIDIA card, verify your CUDA version by running `nvidia-smi` in your terminal.

## Downloading and Running the Installer

The installation process for Windows 11 is straightforward thanks to the official standalone installer. 

Follow these steps to complete the base installation:

1. Navigate to the official Ollama website and locate the download section for Windows.
2. Download the `OllamaSetup.exe` installer file to your local machine.
3. Run the installer executable. You may receive a User Account Control (UAC) prompt asking for permission to make changes to your device. Click yes to continue.
4. Follow the setup wizard prompts. The installer unpacks the necessary binaries, adds the `ollama` CLI tool to your system PATH environment variable, and starts the Ollama background service automatically.

Once the installation finishes, you should see the Ollama icon in your Windows system tray (the notification area on the bottom right of your taskbar). This indicates that the background daemon is running and listening for local requests on port 11434.

Open a new PowerShell or Windows Terminal window and verify the installation by checking the CLI version:

```powershell
ollama --version
```

If the terminal returns the installed version number without throwing command-not-found errors, your environment is correctly configured.

## Pulling and Running Your First Model

With the runtime installed and the background service active, you can now download and execute language models. Ollama uses a library system similar to Docker images. You pull a model tag from the repository, and the runtime handles the weight quantization and context management.

To download and run a standard model like Meta's Llama 3 or Google's Gemma, use the `run` command in your terminal. For instance, to run the Llama 3 8B model, execute:

```powershell
ollama run llama3
```

When you execute this command for the first time, Ollama contacts the remote registry, downloads the model manifest and weight layers in chunks, and loads them into your system memory or VRAM. Depending on your internet connection speed, this download may take a few minutes as model files typically range from 4GB to 5GB in size.

Once the download completes, the terminal transitions into an interactive chat prompt. You can type natural language queries directly into the console. For example:

```text
>>> Write a python function to parse a json log file and extract error codes.
```

The model processes the request locally, utilizing your hardware resources entirely offline. To exit the interactive session and return to the standard PowerShell prompt, type `/exit` or press `Ctrl+D`.

## Managing Models and Integrating via API

Beyond the interactive terminal, Ollama runs a local HTTP server on port 11434, making it accessible to external applications, scripts, and development tools. 

You can manage your downloaded models using standard CLI commands:
- List all locally stored models: `ollama list`
- Inspect model details and parameters: `ollama show llama3`
- Remove a model to free up disk space: `ollama rm llama3`

To verify that the local API server is responding, you can send a standard curl request from a second terminal window:

```powershell
curl http://localhost:11434/api/generate -d '{
  "model": "llama3",
  "prompt": "Why is the sky blue?",
  "stream": false
}'
```

This returns a JSON payload containing the generated response, execution statistics, and token counts. Developers can easily hook this endpoint into custom Python scripts using the `requests` library or official SDKs, enabling local AI capabilities within custom desktop tools, automation scripts, and backend services without exposing data to third-party cloud providers.

## A Practical Option for Windows Users

When you want to expand beyond CLI interactions and are looking for a practical option for Windows users who want a local AI companion with a Live2D face, you can explore [YUNA](https://ko-fi.com/s/45662d5cc0), which integrates smoothly with local backends like Ollama to provide an interactive desktop experience.

---

Disclosure: I am the developer of YUNA, the software mentioned in the last section.
