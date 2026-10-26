# Persistence — kya naye chat me bacha rehta hai

> Ye file sirf theory nahi hai. 26 Oct 2026 ko ek naya sandbox khula aur yahaan
> jo hua, wahi neeche likha hai — observed, assumed nahi.

## TL;DR

| Cheez | Naye chat me? | Kyun |
|---|---|---|
| Code, templates, docs, fonts, presets, tests | ✅ **haan** | git repo me commit hain (branch `arena/9679f9cd-video-creation`) + workspace snapshot me |
| `projects/*/project.json`, `script.md`, `publish.md`, thumbnails, `.srt` | ✅ haan | commit hain (chhoti text/images) |
| **Python packages (`.venv`)** | ❌ **nahi** | `.venv` snapshot se deliberately exclude hai |
| Rendered videos, music beds, generated frames | ❌ nahi | `.gitignore` me hain (repo halka rakhne ke liye) |
| Meri conversation memory (pichhli baat-cheet) | ❌ nahi | model ko naya chat blank milta hai |
| System-installed binaries (apt) | — | is sandbox me apt hi block hai, kuch install nahi hua |

## 26 Oct ko actually kya hua (proof)

Naya sandbox khula, to:

```
git log --oneline -1      → 3c455c1 Initial commit        (mera commit local me gayab)
git ls-files | wc -l      → 1                             (sirf README.md)
ls .venv                  → No such file or directory      (packages gayab)
ls youtube_workspace/     → poora folder maujood ✅        (files bachi rahi)
```

Matlab: **files bachi rahi, git ka local state aur venv nahi.**

Recovery me 2 command lage:

```bash
git fetch origin arena/9679f9cd-video-creation
git reset --mixed cbf8aee        # remote par commit safe tha
```

Uske baad working tree bilkul clean tha — matlab snapshot wali files commit se
byte-for-byte same thi. **GitHub par push kiya hua kaam permanent hai.**
Isliye niyam: kaam khatam hone par commit + push.

Isi audit me ek asli bug bhi pakda gaya: `book_summaries/` folder git me track nahi
tha (git khaali folder track nahi karta), isliye naye chat me wo gayab ho gaya.
Ab har folder me `.gitkeep` hai **aur** `bootstrap.sh` zaroorat par folders khud
bana deta hai — do layer ka bachav.

## Naye chat me kya karna hai (60 second)

```bash
cd /home/user/Video-creation-
git fetch origin arena/9679f9cd-video-creation && git reset --hard origin/arena/9679f9cd-video-creation
bash youtube_workspace/bootstrap.sh --test
```

`git reset --hard` sirf tab chalayein jab local me koi adhoora kaam na ho.
`bootstrap.sh` khud hi venv banata hai, packages daalta hai, folders check karta
hai, aur `check_env.py --strict` + 16 tests chalata hai.

## Meri memory ke bajaye "system ki memory"

Chat badalne par main pichhli baat bhool jaata hoon. Isliye sab kuch files me likha
hai — mujhe sirf ye batana hai ki kaunsa project chal raha hai:

| File | Kaam |
|---|---|
| `README.md` (root) | entry point, 60-second start |
| `youtube_workspace/README.md` | workspace ka naksha, commands, troubleshooting |
| `documentation/TOOLS.md` | har module ka command reference |
| `documentation/WORKFLOW.md` | research → publish ka poora process |
| `documentation/ENVIRONMENT_AUDIT.md` | kya install hua, kya block hai, kyun |
| `documentation/RESUME.md` | naye session ka step-by-step |
| `documentation/PERSISTENCE.md` | yahi file |
| `bootstrap.sh` | environment ko ek command me wapas laata hai |
| `presets/brand.json` | channel ka look (rang, font, margin) |
| `projects/<id>/build_manifest.json` | pichhla build kab, kya, kitna |

Naye chat me bas itna likh dijiye:

```
Workspace ready hai (bootstrap.sh chal chuka).
PROJECT: <id>
NEXT: research / script / narration / build / QC / publish
```

## Jo cheez dobara nahi banegi

- **Meri yaad** — isliye docs.
- **`.venv`** — par `bootstrap.sh` 15–20 s me bana deta hai (pypi.org allowlisted hai).
- **Rendered video** — par pipeline deterministic hai; wahi `project.json` daalne par
  wahi output aata hai (music bhi locally synthesise hota hai, download nahi).

## Jo cheez dobara ban hi nahi sakti (is sandbox me)

- Neural TTS (cloud endpoints blocked) → Arena ka speech tool ya aapki recording.
- Whisper/ASR (Hugging Face blocked) → subtitles script se banti hain.
- Stock footage (koi API nahi) → typography-led visuals + aapki photos.

Ye limits `ENVIRONMENT_AUDIT.md` §3 me tafseel se hain.
