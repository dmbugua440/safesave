import os
base = r'c:\Users\OPEN GATE FOUNDATION\Desktop\backend'
for fn in ['GITHUB_PUSH_INSTRUCTIONS.md','install_python.bat','push_to_github.bat','upload_to_github.py','remove_files_final.bat']:
    p = os.path.join(base, fn)
    if os.path.exists(p):
        os.remove(p)
        print('removed', fn)
    else:
        print('not found', fn)
