"""Native key-entry window for one dynamic provider connection."""

from __future__ import annotations

import sys
import tkinter as tk

from secret_store import save_secret


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    connection_id, connection_name = sys.argv[1], sys.argv[2]

    root = tk.Tk()
    root.title(f"Connect {connection_name} · Poly-LLM Hub")
    root.resizable(False, False)
    root.geometry("490x235")
    root.minsize(490, 235)

    frame = tk.Frame(root, padx=22, pady=18)
    frame.pack(fill="both", expand=True)
    tk.Label(frame, text=f"Connect {connection_name}", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    tk.Label(
        frame,
        text="Paste the API key for this provider connection. The key is saved directly to Windows Credential Manager and is not sent through the browser page.",
        justify="left",
        wraplength=440,
        pady=10,
    ).pack(anchor="w")

    key_var = tk.StringVar()
    entry = tk.Entry(frame, textvariable=key_var, show="•", width=60, font=("Consolas", 10))
    entry.pack(fill="x", pady=(0, 10))
    entry.focus_set()
    status = tk.Label(frame, text="", anchor="w", fg="#9a3412")
    status.pack(fill="x")
    controls = tk.Frame(frame)
    controls.pack(fill="x", pady=(11, 0))

    def save() -> None:
        try:
            save_secret(connection_id, key_var.get())
        except (ValueError, OSError, RuntimeError) as exc:
            status.configure(text=str(exc))
            return
        key_var.set("")
        entry.configure(state="disabled")
        status.configure(text="Saved in Windows Credential Manager.", fg="#166534")
        save_button.configure(state="disabled")
        root.after(900, root.destroy)

    save_button = tk.Button(controls, text="Save key securely", command=save, default="active")
    save_button.pack(side="right")
    root.bind("<Return>", lambda _event: save())
    root.bind("<Escape>", lambda _event: root.destroy())
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
