from PyInstaller.hooks.hookutils import collect_data_files, collect_submodules

hiddenimports = ['pipes'] + collect_submodules('awscli')
datas = collect_data_files('awscli')
