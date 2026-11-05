"""Bundle Qt plugins and the complete recursive MinGW DLL dependency closure."""
import pathlib, re, shutil, subprocess, sys
out, prefix = map(pathlib.Path, sys.argv[1:3])
qt = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else prefix / 'qt6'
index = {p.name.lower(): p for p in pathlib.Path('/source/.cache/cpm').rglob('*.dll')}
index.update({p.name.lower(): p for p in prefix.rglob('*.dll')})
index.update({p.name.lower(): p for p in qt.rglob('*.dll')})
# Use the current compiler's C++ runtime, rather than an older one shipped with a Qt kit.
for name in ('libstdc++-6.dll', 'libgcc_s_seh-1.dll', 'libwinpthread-1.dll'):
    runtime = prefix / 'bin' / name
    if runtime.exists(): index[name] = runtime
for p in out.rglob('*.dll'): index.setdefault(p.name.lower(), p)
for kind in ('platforms', 'imageformats', 'styles', 'tls', 'iconengines'):
    src = qt / 'plugins' / kind
    if src.exists():
        shutil.copytree(src, out / kind, dirs_exist_ok=True)
(out / 'qt.conf').write_text('[Paths]\nPlugins=.\n')
queue = list(out.rglob('*.exe')) + list(out.rglob('*.dll'))
seen = set()
system = {'kernel32.dll','user32.dll','gdi32.dll','advapi32.dll','shell32.dll',
          'ole32.dll','oleaut32.dll','ws2_32.dll','ntdll.dll','msvcrt.dll',
          'shcore.dll','comdlg32.dll','comctl32.dll','winmm.dll','imm32.dll','version.dll',
          'setupapi.dll','dwmapi.dll','uxtheme.dll','opengl32.dll','glu32.dll',
          'ncrypt.dll','bcrypt.dll','crypt32.dll','secur32.dll','iphlpapi.dll','netapi32.dll',
          'userenv.dll','wtsapi32.dll','dnsapi.dll','normaliz.dll','shlwapi.dll',
          'winspool.drv','d3d11.dll','dxgi.dll','d3d9.dll','dwrite.dll',
          'd2d1.dll','d3d12.dll','dxcore.dll','powrprof.dll','propsys.dll',
          'cfgmgr32.dll','hid.dll','winhttp.dll','wininet.dll','ucrtbase.dll',
          'avrt.dll','authz.dll','mpr.dll','msimg32.dll','psapi.dll','rpcrt4.dll',
          'dsound.dll','mf.dll','mfplat.dll','mfuuid.dll','strmiids.dll','vulkan-1.dll'}
while queue:
    binary = queue.pop()
    if binary in seen: continue
    seen.add(binary)
    imports = subprocess.check_output(['x86_64-w64-mingw32.shared-objdump', '-p', str(binary)], text=True)
    for name in re.findall(r'DLL Name:\s*(\S+)', imports):
        key = name.lower()
        if key in system or key.startswith(('api-ms-', 'ext-ms-')): continue
        if key not in index: raise RuntimeError(f'Unresolved DLL {name} required by {binary}')
        target = out / index[key].name
        if not target.exists():
            shutil.copy2(index[key], target)
            queue.append(target)
