# 🔐 CipherPixel – Advanced Image Security System

**Secure your images. Preserve every byte.**

CipherPixel is a desktop-based image encryption and decryption application built with **Python and PySide6**. It encrypts images into authenticated `.cpx` files and restores them **byte-for-byte** using industry-standard cryptographic algorithms.

Powered by **AES-256-GCM, Argon2id, and PBKDF2-HMAC-SHA256**, CipherPixel provides strong encryption, integrity verification, and secure local processing.

- 🔒 Advanced image encryption
- 🛡️ Authentication and tamper detection
- 🔑 Password-based key derivation
- 🖥️ Modern PySide6 desktop interface
- 💻 Fully offline – no network communication

---
## ✨ Key Features

### 🔐 Advanced Encryption
- AES-256-GCM authenticated encryption.
- Argon2id and PBKDF2-HMAC-SHA256 key derivation.
- Random salt and nonce generation.
- Chunk-based encryption for large images.

### 🛡️ Security & Integrity
- Authentication of encrypted data.
- Detection of modified, corrupted, or truncated files.
- Protection against chunk reordering and duplication.
- Secure temporary-file handling.
- Password and key information never stored in history or logs.

### 🖼️ Image Processing
- Supports PNG, JPG, JPEG, BMP, and TIFF.
- Exact byte-for-byte image restoration.
- Preserves original metadata and image properties.
- Preview images before encryption and after decryption.

### 🖥️ User Interface
- Modern PySide6 graphical interface.
- Dark and light themes.
- Drag-and-drop image selection.
- Password strength indicator and generator.
- Encryption progress with cancellation.
- File history with search, filtering, and CSV export.

### ⚙️ Additional Features
- Configurable encryption strength.
- Security Center with live self-test.
- Custom export directory.
- Application settings and restore defaults.
- Keyboard shortcuts for navigation.

---

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python 3.11+ | Core application development |
| PySide6 | Desktop graphical interface |
| Cryptography | AES-256-GCM encryption |
| Argon2-cffi | Argon2id key derivation |
| PBKDF2-HMAC-SHA256 | Alternative key derivation |
| SQLite | Local application history |
| Pytest | Automated testing |

---

## 🚀 Installation & Setup

### Prerequisites

- Windows 10/11, macOS, or Linux
- Python 3.11 or newer
- Git

### 1. Clone the repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd CipherPixel
```

### 2. Create a virtual environment

**Windows (PowerShell):**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Run the application

```bash
python main.py
```

The CipherPixel desktop application will launch.

---

## 🔑 How to Use

### 1. Encrypt an Image

1. Open the **Encrypt Image** page.
2. Select an image using drag-and-drop or file browsing.
3. Preview the selected image and its properties.
4. Enter a strong password or generate one.
5. Choose the desired encryption configuration.
6. Click **ENCRYPT IMAGE**.
7. Wait for encryption to complete.
8. Save the generated `.cpx` file.

### 2. Decrypt an Image

1. Open the **Decrypt Image** page.
2. Select the encrypted `.cpx` file.
3. Enter the original encryption password.
4. Click **DECRYPT IMAGE**.
5. Verify the restored image preview.
6. Export the decrypted image.

> ⚠️ **Important:** Passwords cannot be recovered. Always remember your encryption password. Encryption does not automatically delete the original image.

---

## 🧠 Encryption Architecture

CipherPixel uses authenticated encryption with password-based key derivation.

### Encryption Workflow

```text
       User Password
             |
          NFKC
             |
             v
      Key Derivation
      (Argon2id / PBKDF2)
             |
             v
       256-bit Key
             |
             v
      AES-256-GCM
             |
             v
    Chunk-based Encryption
             |
             v
       Authenticated
         .cpx File
```

### `.cpx` File Format – Version 1

| Component | Description |
|---|---|
| Header | 48-byte plaintext authenticated header |
| Metadata | Encrypted JSON containing filename, format, size, dimensions, and SHA-256 |
| Data Chunks | Encrypted image data in chunks of up to 1 MiB |
| Final Chunk | Authenticated final chunk for truncation detection |

### Security Mechanisms

- **AES-256-GCM:** Provides authenticated encryption.
- **Argon2id:** Memory-hard password-based key derivation.
- **PBKDF2-HMAC-SHA256:** Alternative key derivation mechanism.
- **Random Salt:** Fresh 128-bit salt for each encrypted file.
- **Nonce Management:** 96-bit nonces constructed from a random 64-bit prefix and a 32-bit counter.
- **Authenticated Additional Data (AAD):** Protects header information, chunk types, and ordering.
- **SHA-256:** Verifies restored image integrity.
- **Atomic Decryption:** Output is committed only after successful authentication and verification.

---

## ⚙️ Key Derivation Presets

CipherPixel provides three configurable security levels.

| Security Level | Argon2id | PBKDF2-HMAC-SHA256 |
|---|---|---|
| Balanced (Default) | 64 MiB · 3 passes · 4 lanes | 600,000 iterations |
| Strong | 256 MiB · 4 passes · 4 lanes | 1,200,000 iterations |
| Maximum | 512 MiB · 5 passes · 4 lanes | 3,000,000 iterations |

The selected parameters are stored inside each encrypted file, ensuring previously encrypted files remain compatible even when default settings change.

---

## 📂 Project Structure

```text
CipherPixel/
│
├── main.py
│
├── core/
│   ├── encryption.py
│   ├── decryption.py
│   ├── cpx_format.py
│   ├── key_manager.py
│   ├── file_handler.py
│   ├── security_utils.py
│   ├── history.py
│   ├── selftest.py
│   └── errors.py
│
├── ui/
│   ├── components/
│   ├── theme.py
│   ├── workers.py
│   └── application pages
│
├── utils/
│   ├── settings
│   ├── logger
│   ├── paths
│   └── validators
│
├── tests/
│
├── assets/
│   └── fonts/
│
├── docs/
│   └── screenshots/
│
├── tools/
│   └── make_screenshots.py
│
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

---

## 🧪 Testing & Quality Assurance

CipherPixel includes **176 automated tests** covering encryption, decryption, security, and GUI functionality.

### Test Coverage

- Exact byte-for-byte image restoration.
- PNG, JPG, JPEG, BMP, and TIFF support.
- Incorrect password handling.
- Tampered header and encrypted data detection.
- Chunk modification, duplication, reordering, and removal.
- File truncation and corruption detection.
- Nonce and salt uniqueness.
- Invalid encryption parameters.
- Unsupported and disguised image files.
- Cancellation and temporary-file handling.
- History privacy and SQL/LIKE safety.
- Settings validation.
- End-to-end GUI tests using real buttons and worker threads.

### Run Tests

Install development dependencies:

```bash
pip install -r requirements-dev.txt
```

Run the complete test suite:

```bash
python -m pytest
```

Run core encryption and security tests without GUI tests:

```bash
python -m pytest tests/test_encryption.py tests/test_decryption.py tests/test_security.py
```

---

## ⚠️ Limitations & Security Considerations

- The application has not undergone an independent security audit.
- Python cannot reliably zero password strings from memory.
- Temporary files are deleted on application exit, but deletion is not guaranteed secure erasure on SSDs.
- Use full-disk encryption such as BitLocker or FileVault for additional protection.
- Password strength estimation is heuristic-based.
- Original images are not automatically deleted after encryption.
- GIF, WebP, and animated image formats are not supported.
- High-security Argon2id settings require additional memory.

**Security Recommendation:** Use a long, unique passphrase or the built-in password generator. Keep backups of encrypted files and their passwords.

---

## 🔧 Troubleshooting

| Issue | Solution |
|---|---|
| Python not recognized | Install Python and enable Add Python to PATH. |
| PySide6 module not found | Activate the virtual environment and install requirements. |
| Package installation fails | Upgrade pip and use 64-bit Python 3.11–3.13. |
| Argon2id unavailable | Install `argon2-cffi`. |
| Qt platform plugin error on Linux | Install `libxcb-cursor0`, `libxkbcommon-x11-0`, and `libegl1`. |
| Decryption failed | Verify your password and check whether the encrypted file was modified. |
| Integrity check failed | The encrypted file may be corrupted or truncated. |
| Insufficient memory | Select a lower encryption security level. |
| Insufficient disk space | Free up space on the destination drive. |

Application logs are available at:

```text
data/logs/cipherpixel.log
```

Logs do not contain passwords or image data.

To regenerate application screenshots:

```bash
python tools/make_screenshots.py
```

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl + 1` to `Ctrl + 7` | Switch between application pages |

---

## 🔒 Privacy

CipherPixel is designed for completely local operation.

- No cloud uploads.
- No external network communication.
- No password or encryption-key persistence.
- No image data stored in application history.
- Local processing and file management.

Your images remain on your device.

---

## 👨‍💻 Developer

**Developed as a desktop application project focused on image security, cryptography, and data integrity.**

---

## 📜 License

Add your preferred open-source license here. If you intend to distribute this project, include the corresponding `LICENSE` file.

---

⭐ **If you find CipherPixel useful, consider giving the repository a star!**
