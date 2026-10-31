Set fs = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = fs.GetParentFolderName(WScript.ScriptFullName)
py = fs.BuildPath(sh.CurrentDirectory, ".venv\Scripts\pythonw.exe")
If Not fs.FileExists(py) Then py = "pythonw.exe"
sh.Run """" & py & """ """ & fs.BuildPath(sh.CurrentDirectory, "app.py") & """", 0, False
