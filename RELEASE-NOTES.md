# Grove 1.2.0

Set up a new computer in one go.

- **Set up your apps:** the first time Grove opens, it shows every app with a checkbox. All are ticked; untick any you don't want, or use Select all and Select none, then press Install selected. Everything installs together, with one password prompt.
- Each app shows its own progress: downloading, installing, then installed.
- Anything the apps need from your system's software sources, such as Python, is installed with them.
- **Shell extensions** are set to turn on, and Grove asks you to log out once at the end instead of once per extension. Installing an extension from its card turns it on too.
- **Ollama for Fleece:** when Fleece is ticked and Ollama is missing, the list adds Ollama. It is installed with the official installer from ollama.com, in the same password prompt.
- Apps that are already installed and up to date are listed and left alone. Apps made for another kind of computer show as not available, on their cards too.
- Open the checklist again at any time from the new menu at the top right, which also has About Grove.

Install:

```bash
sudo apt install ./grove_1.2.0_all.deb
```
