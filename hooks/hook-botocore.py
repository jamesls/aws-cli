from PyInstaller.hooks.hookutils import collect_data_files

hiddenimports = ['ConfigParser', 'HTMLParser', 'markupbase']
datas = collect_data_files('botocore')
