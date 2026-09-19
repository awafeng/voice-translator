# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置（阶段12）
# onefile 太慢(解压到临时目录含145MB模型)，用 onedir：启动快、结构清晰

a = Analysis(
    ['gui/app.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 模型随包（models -> 内嵌资源）
        ('models/moonshine-en-tiny', 'models/moonshine-en-tiny'),
        ('models/opus-mt-en-zh-ct2-int8', 'models/opus-mt-en-zh-ct2-int8'),
        ('models/opus-mt-en-zh-tokenizer', 'models/opus-mt-en-zh-tokenizer'),
        ('models/piper-zh', 'models/piper-zh'),
        ('models/silero-vad', 'models/silero-vad'),
        # TinyTTS 文本前端第三方数据（CMU 字典等）
        ('third_party/tiny_tts_text', 'third_party/tiny_tts_text'),
        ('third_party/piper_zh', 'third_party/piper_zh'),
        # unicode_rbnf 的语言规则 XML（动态 glob 加载，静态扫描收不到）
        ('venv/Lib/site-packages/unicode_rbnf/rbnf', 'unicode_rbnf/rbnf'),
        # moonshine_voice 的原生 DLL（运行时 CDLL 加载，静态扫描收不到；
        # 它按 __file__ 同目录查找，所以必须放进 moonshine_voice/ 下）
        ('venv/Lib/site-packages/moonshine_voice/moonshine.dll',
         'moonshine_voice'),
        ('venv/Lib/site-packages/moonshine_voice/onnxruntime.dll',
         'moonshine_voice'),
    ],
    hiddenimports=[
        'unicode_rbnf',
        'sentence_stream',
        'transformers',
        'transformers.models.bert',
        'transformers.models.bert.tokenization_bert',
        'transformers.tokenization_utils',
        'sacremoses',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 体积纪律：明确排除重型/无用库
        'torch', 'tensorflow', 'jax',
        'matplotlib', 'pandas', 'scipy',
        'IPython', 'jedi', 'pytest',
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VoiceTranslator-EN2ZH',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI 程序，不弹黑窗
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='VoiceTranslator-EN2ZH',
)
