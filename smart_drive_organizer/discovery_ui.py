from __future__ import annotations
import tkinter as tk
from tkinter import messagebox, ttk
from .models import DiscoveryGroup

class DiscoveryReviewDialog(tk.Toplevel):
    """Review, rename and approve recurring filename patterns."""
    def __init__(self, parent: tk.Misc, groups: list[DiscoveryGroup]):
        super().__init__(parent)
        self.title("Review discovered file groups")
        self.geometry("940x640")
        self.minsize(800, 540)
        self.transient(parent); self.grab_set()
        self.groups=list(groups); self.names=[g.suggested_name for g in groups]
        self.result=None
        bg,black,white,red="#F4F4F5","#101010","#FFFFFF","#D71920"
        self.configure(bg=bg)
        style=ttk.Style(self)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("TFrame",background=bg)
        style.configure("TLabel",background=bg,foreground=black,font=("Segoe UI",9))
        style.configure("Title.TLabel",background=bg,foreground=black,font=("Segoe UI",18,"bold"))
        style.configure("TButton",font=("Segoe UI",9),padding=(9,7))
        style.configure("Primary.TButton",background=red,foreground=white,font=("Segoe UI",9,"bold"),padding=(12,8))
        style.configure("Treeview",rowheight=26,font=("Segoe UI",9))
        style.configure("Treeview.Heading",background=black,foreground=white,font=("Segoe UI",9,"bold"),padding=7)
        outer=ttk.Frame(self,padding=14); outer.pack(fill="both",expand=True)
        ttk.Label(outer,text="Recurring file-name patterns",style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer,text=(f"{len(groups)} suggestions found. Each pattern occurs in at least two distinct files. "
            "Nothing has been moved, copied, renamed or created."),wraplength=880).pack(anchor="w",pady=(5,12))
        body=ttk.Frame(outer); body.pack(fill="both",expand=True)
        left=ttk.Frame(body); left.pack(side="left",fill="both",expand=True)
        cols=("phrase","category","count","folder")
        self.tree=ttk.Treeview(left,columns=cols,show="headings",selectmode="extended")
        for col,title,width in [("phrase","Repeated wording",190),("category","File family",100),("count","Files",55),("folder","Suggested folder",180)]:
            self.tree.heading(col,text=title); self.tree.column(col,width=width,minwidth=50,anchor="center" if col=="count" else "w")
        sb=ttk.Scrollbar(left,orient="vertical",command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set); self.tree.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
        for i,g in enumerate(groups): self.tree.insert("","end",iid=str(i),values=(g.phrase,g.category,g.file_count,self.names[i]))
        self.tree.bind("<<TreeviewSelect>>",self._changed)
        pane=ttk.LabelFrame(body,text="Selected suggestion",padding=9); pane.pack(side="left",fill="both",padx=(10,0))
        self.info=tk.StringVar(value="Select a row.")
        ttk.Label(pane,textvariable=self.info,wraplength=245).pack(anchor="w",pady=(0,8))
        ttk.Label(pane,text="Folder name").pack(anchor="w")
        self.name=tk.StringVar()
        ttk.Entry(pane,textvariable=self.name,width=30).pack(fill="x",pady=4)
        ttk.Button(pane,text="Update folder name",command=self._rename).pack(anchor="w",pady=(0,8))
        ttk.Label(pane,text="Example files / locations").pack(anchor="w")
        self.examples=tk.Text(pane,width=31,height=12,wrap="word",font=("Segoe UI",8))
        self.examples.pack(fill="both",expand=True)
        self.examples.configure(state="disabled")
        actions=ttk.Frame(outer); actions.pack(fill="x",pady=(10,0))
        ttk.Button(actions,text="Select all",command=lambda:self.tree.selection_set(tuple(str(i) for i in range(len(groups))))).pack(side="left")
        ttk.Button(actions,text="Clear",command=lambda:self.tree.selection_remove(self.tree.selection())).pack(side="left",padx=5)
        ttk.Button(actions,text="Cancel",command=self.destroy).pack(side="right")
        ttk.Button(actions,text="Remember rejection",command=self._reject).pack(side="right",padx=(0,6))
        ttk.Button(actions,text="Approve selected & rescan",style="Primary.TButton",command=self._approve).pack(side="right",padx=(0,8))
        if groups: self.tree.selection_set("0"); self._changed()

    def _ids(self): return [int(x) for x in self.tree.selection()]

    def _changed(self,_event=None):
        ids=self._ids()
        if len(ids)!=1:
            self.info.set(f"{len(ids)} suggestions selected. Select one to rename."); return
        i=ids[0]; g=self.groups[i]; self.name.set(self.names[i])
        self.info.set(f"Pattern: {g.phrase}\nType: {g.category}\nMatches: {g.file_count} different files")
        lines=[f"{n}\n{p}" for n,p in zip(g.sample_files,g.sample_locations)]
        self.examples.configure(state="normal"); self.examples.delete("1.0","end")
        self.examples.insert("1.0","\n\n".join(lines)); self.examples.configure(state="disabled")

    def _rename(self):
        ids=self._ids()
        if len(ids)!=1:
            messagebox.showinfo("Select one row","Select exactly one suggestion before renaming.",parent=self); return
        value=" ".join(self.name.get().split()).strip(" .")
        if not value:
            messagebox.showwarning("Name required","Enter a folder name.",parent=self); return
        if any(c in value for c in '<>:"/\\|?*'):
            messagebox.showwarning("Invalid name",'Remove < > : " / \\ | ? * characters.',parent=self); return
        i=ids[0]; self.names[i]=value[:100]; self.tree.set(str(i),"folder",self.names[i])

    def _approve(self):
        ids=self._ids()
        if not ids:
            messagebox.showinfo("No selection","Select at least one suggested group.",parent=self); return
        self.result={"decision":"approved","groups":[{"name":self.names[i],"phrase":self.groups[i].phrase,
            "category":self.groups[i].category,"file_count":self.groups[i].file_count} for i in ids]}
        self.destroy()

    def _reject(self):
        ids=self._ids()
        if not ids:
            messagebox.showinfo("No selection","Select one or more suggestions to remember as rejected.",parent=self); return
        self.result={"decision":"rejected","groups":[{"name":self.names[i],"phrase":self.groups[i].phrase,
            "category":self.groups[i].category,"file_count":self.groups[i].file_count} for i in ids]}
        self.destroy()
