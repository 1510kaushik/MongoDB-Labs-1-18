# Windows Threat Chat

**Submitted by:** Kaushik M  
**USSN:** 24BTRCL 224

This standalone Windows chatbot reads selected security signals and uses a local Ollama model to explain findings and suggest manual verification steps. It checks Defender status and recent events, firewall profiles, and installed hotfix history. No security settings are changed.

## Run on Windows

1. Extract the entire ZIP.
2. Install Python 3.10 or newer and Ollama if needed.
3. Run `ollama pull llama3.2:3b` once in PowerShell.
4. Double-click `Start_Windows_Threat_Chat.cmd`. Keep its window open.
5. In the browser, open http://127.0.0.1:8765/chat/ and select **Assess this laptop**.
6. Ask **What did my laptop assessment find, and what should I investigate first?**

The launcher can start Ollama if needed. If the model is unavailable, the chatbot returns evidence-based assessment guidance. The assessment covers selected security signals and cannot determine whether the laptop is free of threats.

No Docker, MongoDB server, cloud API key, or labs ZIP is needed for this standalone version. Windows is required for live host probes.

## Files

- `chat/server.py` runs the local assessment and chat service.
- `chat/index.html` contains the browser interface.
- `Start_Windows_Threat_Chat.cmd` starts the server.
