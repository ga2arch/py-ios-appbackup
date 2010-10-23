from optparse import OptionParser
from datetime import datetime
import paramiko
import socket
import time
import sys
import os

class Apps:
    appsdir = '/var/mobile/Applications/'
    
    def get_app_name(self, names):
        for filename in names:
            raw1 = filename.split('.')
            if len(raw1) == 2:
                raw2 = filename.split('.')[-1].strip('\n')
                if raw2 == 'app':
                    return raw1[0]
        return False

    def isdir(self, directory):
        command = '[ -d %s ] && echo "ok"' % (directory, )
        stdin, stdout, stderr = self.ssh.exec_command(command)
        response = stdout.readlines()
        if response:
            return True
        else:
            return False

    def get_apps_number(self, ssh):
        command = 'ls %s' % (self.appsdir,)
        stdin, stdout, stderr = ssh.exec_command(command)
        raw_apps = stdout.readlines()
        return len(raw_apps)
        
    def get_apps_names(self, ssh):
        command = 'ls %s' % (self.appsdir,)
        apps = {}
        stdin, stdout, stderr = ssh.exec_command(command)
        raw_apps = stdout.readlines()
        for e, raw_app in enumerate(raw_apps):
            command = 'ls %s%s' % (self.appsdir, raw_app.rstrip('\n'))
            stdin, stdout, stderr = ssh.exec_command(command)
            files = stdout.readlines()
            for f in files:
                if f.split('.')[-1].strip('\n') == 'app':
                    appname = f.split('.')[0]
                    apps[raw_app] = appname
        return apps

class AppsBackup(Apps):
    def __init__(self, ssh):
        self.ssh = ssh
    
    def start_backup(self, dst):
        self.sftp = ssh.open_sftp()
        self.copytree(self.appsdir, dst)
        self.sftp.close()
        self.ssh.close()

    def copytree(self, src, dst):
        names = self.sftp.listdir(src)
        if not os.path.isdir(dst):
            os.makedirs(dst)
        appname = self.get_app_name(names)
        if appname:
            print 'Backing up ' + appname
            names.remove('%s.app' % (appname,))
            filepath = '%s/appname' % (dst,) 
            f = open(filepath,'w')
            f.write(appname)
            f.close()
        
        for name in names:
            srcname = os.path.join(src, name)
            dstname = os.path.join(dst, name)
            if self.isdir(srcname):
               self.copytree(srcname, dstname)
            else:
               self.sftp.get(srcname, dstname)
               stats = self.sftp.stat(srcname)
               os.utime(dstname, (stats.st_atime, stats.st_mtime))

class AppsUpdate(Apps):
    def __init__(self, ssh):
        self.ssh = ssh
    
    def start_update(self, dst):
        self.sftp = ssh.open_sftp()
        self.copytree(self.appsdir, dst)
        self.sftp.close()
        self.ssh.close()

    def copytree(self, src, dst):
        names = self.sftp.listdir(src)
        if not os.path.isdir(dst):
            os.makedirs(dst)
        appname = self.get_app_name(names)
        if appname:
            self.appname = appname
            names.remove('%s.app' % (appname,))

        for name in names:
            srcname = os.path.join(src, name)
            dstname = os.path.join(dst, name)
            if self.isdir(srcname):
               self.copytree(srcname, dstname)
            else:
               try:
                   srcstats = self.sftp.stat(srcname)
                   dststats = os.stat(dstname)
                   if srcstats.st_mtime > dststats.st_mtime:
                       self.sftp.get(srcname, dstname)
                       print 'Updating ' + self.appname
                       os.utime(dstname, (srcstats.st_atime, srcstats.st_mtime))
               except OSError:
                   self.sftp.get(srcname, dstname)
                   stats = self.sftp.stat(srcname)
                   os.utime(dstname, (stats.st_atime, stats.st_mtime))

class AppsRestore(Apps):
    def __init__(self, ssh):
        self.ssh = ssh
        
    def start_restore(self, src):
        self.sftp = ssh.open_sftp()
        self.copytree(src, self.appsdir)
        self.sftp.close()
        self.ssh.close()

    def copytree(self, src, dst):
        names = os.listdir(src)
        if 'appname' in names:
            filepath = '%s/appname' % (src, )
            f = open(filepath,'r')
            appname = f.readlines()[0].rstrip('\n')
            print 'Restoring ' + appname
            names.remove('appname')
            
        if not self.isdir(dst):
            folders = dst.split(self.appsdir)[-1].split('/')
            if folders:
                for e,folder in enumerate(folders):
                    r = '%s%s/%s' % (self.appsdir, '/'.join(folders[:e]), folder)
                    self.sftp.mkdir(r)

        for name in names:
            srcname = os.path.join(src, name)
            dstname = os.path.join(dst, name)
            if os.path.isdir(srcname):
               self.copytree(srcname, dstname)
            else:
               try:
                   self.sftp.stat(dstname)
               except IOError:
                   self.sftp.put(srcname, dstname)

if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option('-i', '--ip', dest='ip', metavar='IP')
    parser.add_option('-p', '--password', dest='password', metavar='PASSWORD', 
                      default='alpine')
    parser.add_option('-b', '--backup', action='store_true')
    parser.add_option('-u', '--update', action='store_true')
    parser.add_option('-r', '--restore', action='store_true')
    parser.add_option('-f', '--folder', dest='folder', default='.', metavar='FOLDER')
    (options, args) = parser.parse_args()

    if options.ip:
        appsdir = '/var/mobile/Applications/'
        print 'Connecting SSH ....'
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(options.ip, username='root', password=options.password,
                        timeout=10)
        except Exception:
            print 'Error connecting to your idevice, check the ip and/or password'
            sys.exit(1)
            
        if options.backup:
            appsnumber = Apps().get_apps_number(ssh) 
            message = 'Found %s Apps' % (str(appsnumber), )
            print message
            folder = '%s/iab_%s' % (options.folder, str(time.time()))
            AppsBackup(ssh).start_backup(folder)

        if options.update:
            revisions = [f for f in os.listdir(options.folder) if f.startswith('iab_')]
            revisions.sort()
            print 'Found %s revisions:' % (str(len(revisions))) 
            for e, revision in enumerate(revisions):
                d = datetime.fromtimestamp(float(revision.split('_')[-1]))
                print '%s) %s' % (e, d)
            rnumber = int(raw_input('Update revision: '))
            folder = '%s%s' % (options.folder, revisions[rnumber])
            AppsUpdate(ssh).start_update(folder)
            
        if options.restore:
            revisions = [f for f in os.listdir(options.folder) if f.startswith('iab_')]
            revisions.sort()
            print 'Found %s revisions:' % (str(len(revisions))) 
            for e, revision in enumerate(revisions):
                d = datetime.fromtimestamp(float(revision.split('_')[-1]))
                print '%s) %s' % (e, d)
            rnumber = int(raw_input('Restore revision: '))
            folder = '%s%s' % (options.folder, revisions[rnumber])
            AppsRestore(ssh).start_restore(folder)
   
    