<img width="1085" height="821" alt="Screenshot 2026-05-29 205717" src="https://github.com/user-attachments/assets/f91c5807-e0f2-4281-bde6-946d26bbbf36" />


# Scrivener Converter

A Windows desktop app for converting between Ulysses and Scrivener project formats in both directions.

## Download

Download **`Scrivener Converter.exe`** from this repository. No installation or Python required just run the exe.

> **Note:** Windows may show a "Windows protected your PC" SmartScreen warning the first time you run it. This is normal for unsigned apps. Click **More info → Run anyway** to proceed.

---

## How to Use

### Tab 1 Ulysses → Scrivener

Converts Ulysses projects into Scrivener or a folder of RTF files.

1. Drag your `.ulproj` file(s) into the file list, or click **Browse**
2. Choose an output folder
3. Select a conversion mode:
   - **Extract to folder** saves each sheet as an `.rtf` file in a folder tree that mirrors your Ulysses group structure
   - **Convert to Scrivener project** creates a `.scriv` folder you can open directly in Scrivener 3 for Windows
4. Click **Convert**

> When opening the converted `.scriv` project in Scrivener, expand the **Main** folder in the binder panel on the left to see your documents.

---

### Tab 2 Scrivener → Export

Extracts a Scrivener project to a folder of RTF files.

1. Click **Browse** and select your `.scriv` folder
2. Choose an output folder
3. Click **Extract to RTF Directory**

Each document is saved as `{Title}.rtf` inside a folder structure that matches your Scrivener binder.

---

## Notes

- Images (JPEG and PNG) are embedded directly into the converted RTF files
- Output uses Georgia 16pt to match Scrivener's default document style
- Only `.ulproj` files support Scrivener project conversion; `.textpack` and `.md` files export to directory only
- Targets **Scrivener 3 for Windows**
