#!/usr/bin/env python
#coding: utf-8
import logging
import re
import time
from multiprocessing import Pool,Queue
import sys
from ConfigParser import ConfigParser
import requests
import json
from pprint import pprint
import csv
import signal
import os
from os import path
import paramiko
#from Queue import Queue
import sys
reload(sys)

sys.setdefaultencoding('utf-8')

# the qvm is the queue for the vm is not downloadeds
qvm = Queue()
# the qdown is queue for vm has downloaded
qdown = Queue()


def InitLog(filename, console=True):
    logger = logging.getLogger(filename)
    logger.setLevel(logging.DEBUG)

    logpath = "/var/log/vmconvert/" + filename + ".log"
    fh = logging.FileHandler(logpath)
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    ch.setFormatter(formatter)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    if console:
        logger.addHandler(ch)

    return logger


def diskusage(path, unit=None):
    d = os.statvfs(path)
    freeDisk = d.f_bavail * d.f_frsize

    if unit == "KB":
        freeDisk = freeDisk / 1024
    elif unit == "MB":
        freeDisk = freeDisk / (1024 * 1024)
    elif unit == "GB":
        freeDisk = freeDisk / (1024 * 1024 * 1024)

    return freeDisk


def tryencode(name):
    try:
        name = name.decode("gbk")
        return name
    except Exception as e:
        return name


class shex(object):
    def __init__(self, exsi, exsipass, vmname, logfile):
        self.exsi = exsi
        self.exsipass = exsipass
        self.vmname = vmname
        self.logfile = logfile

    def writepass(self):
        with open(".esxpasswd", "w") as wf:
            wf.write(self.exsipass)

    def VirtDown(self):
        """download the vmdk file to local system"""
        self.logfile.info("Download command start.....")
        from sh import virt_v2v_copy_to_local
        self.writepass()
        cmd = "virt-v2v-copy-to-local -v -ic esx://root@%s?no_verify=1 --password-file .esxpasswd %s"
        cmd = cmd % (self.exsi, self.vmname)
        cmd = cmd.split()[1:]
        stderrfilename = self.vmname + ".output"

        try:
            self.logfile.info("Excute command: %s" % cmd)
            self.logfile.info("Download vm: %s" % self.vmname)
            proc = virt_v2v_copy_to_local(*cmd, _iter=True, _err=stderrfilename)
        except Exception as e:
            self.logfile.critical("Excute command faild: %s " % cmd)
            self.logfile.critical(e)
            return None

        msg = "Download the vmdk:%s from exsi:%s " % (self.vmname, self.exsi)
        self.logfile.info(msg)
        for line in proc:
            self.logfile.info(line)
            length = shex.getLength(stderrfilename)
            if length:
                msg = "VMDK size is Length: %s " % length
                self.logfile.info(msg)
                sysdisk = diskusage("./")
                with open(stderrfilename, "w") as wf:
                    wf.truncate()
                if length * 1.5 > sysdisk:
                    self.logfile.critical("WTF the disk usage")
                    self.logfiel.critical("Try to kill the process and delete the vmdk")
                    proc.process.signal(signal.SIGINT)
                    self.logfile.critical("the vm is too big!!!!")
                    self.remove(self.vmname)
                    return None

        msg = "Command return code: %s" % proc.exit_code
        self.logfile.info(msg)

        ret = not proc.exit_code

        if ret:
            if not os.path.exists(".vm"):
                os.mkdir(".vm")
                self.logfile.info("Download completed")
            open(".vm/" + self.vmname + ".download", "a").close()
        else:
            msg = "Download faild for some reasone, excute the command manually for review: %s " % cmd
            self.logfile.info()

        return ret

    def VirtConvert1(self, out="./"):
        """"convert the vm to qcow2 format with virt-v2v"""
        self.logfile.info("Convert1 command start.....")
        from sh import virt_v2v
        vm = self.vmname + "-disk1"
        cmd = "virt-v2v -v -i disk %s -of qcow2 -o local -os %s "
        cmd = cmd % (vm, out)
        cmd = cmd.split()[1:]

        try:
            self.logfile.info("Excute command: %s" % cmd)
            self.logfile.info("Convert vm: %s" % self.vmname)
            proc = virt_v2v(*cmd, _iter=True)
        except Exception as e:
            self.logfile.critical("Excute command failed: %s " % cmd)
            self.logfile.critical(e)
            return False

        for line in proc:
            self.logfile.info(line)

        ret = not proc.exit_code

        if ret:
            if not os.path.exists(".vm"):
                os.mkdir(".vm")
            self.logfile.info("Converte completed.....")
            open(".vm/" + self.vmname + ".convert", "a").close()
            os.rename(vm + "-sda", vm[:-6] + "-qcow2")
            self.logfile.info("Remove the original vmdk file")
            tmpret = shex.remove(vm)
            if tmpret:
                self.logfile.info("Remove the original vmdk file failed")
                self.logfile.critical(tmpret)
        return ret

    def VirtConvert2(self, out="./"):
        """"convert the vm to qcow2 format with qemu-img"""
        self.logfile.info("Convert1 command start.....")
        from sh import qemu_img
        vm = self.vmname + "-disk1"
        cmd = "qemu-img convert -O qcow2 %s %s%s-qcow2"
        cmd = cmd % (vm, out, self.vmname)
        cmd = cmd.split()[1:]

        try:
            self.logfile.info("Excute command: %s" % cmd)
            self.logfile.info("Convert vm: %s" % self.vmname)
            proc = qemu_img(*cmd, _iter=True)
        except Exception as e:
            self.logfile.critical("Excute command failed: %s " % cmd)
            self.logfile.critical(e)
            return False

        for line in proc:
            self.logfile.info(line)

        ret = not proc.exit_code

        if ret:
            if not os.path.exists(".vm"):
                os.mkdir(".vm")
            self.logfile.info("Converte completed.....")
            open(".vm/" + self.vmname + ".convert", "a").close()
            self.logfile.info("Remove the original vmdk file")
            tmpret = shex.remove(vm)
            if tmpret:
                self.logfile.info("Remove the original vmdk file failed")
                self.logfile.critical(tmpret)
        return ret

    def poweroff(self, release, server, username, password):
        """try poweroff the vm"""
        if release.lower() != "windows":
            if release == "centos6" or release == "redhat7":
                try:
                    self.cleanNet(release, server, username, password)
                    ret = self.shutdown(server, username, password)
                    time.sleep(10)
                except Exception as e:
                    msg = "Poweroff failed....."
                    self.logfile.critical(msg)
                    self.logfile.critical(e)
                    return False

            else:
                try:
                    ret = self.shutdown(server, username, password)
                    time.sleep(10)
                except Exception as e:
                    msg = "Poweroff failed....."
                    self.logfile.critical(msg)
                    self.logfile.critical(e)
                    return False
            return ret

    @staticmethod
    def getLength(fname):
        """get the vm disk size"""
        lengthre = re.compile(r"Content-Length: (\d+)")
        length = None
        with open(fname) as rf:
            retline = rf.read()
            length = lengthre.findall(retline)
            if len(length) > 0:
                length = int(length[0])

        return length

    @staticmethod
    def remove(fname):
        """remove the vm fiel"""
        if path.isfile(fname):
            try:
                os.remove(fname)
                return None
            except Exception as e:
                return e
        else:
            msg = "Not a file: %s" % fname
            return msg

    def cleanNet(self, release, server, username, password):
        """clean up the network configuration"""
        command7 = """cp /etc/sysconfig/network-scripts/ifcfg-eth0 /root/ifcfg-eth0;echo "TYPE=Ethernet
BOOTPROTO=dhcp
NAME=eth0
DEVICE=eth0
ONBOOT=yes" > /etc/sysconfig/network-scripts/ifcfg-eth0
"""
        command6 = """cp /etc/sysconfig/network-scripts/ifcfg-eth0 /root/ifcfg-eth0;echo "DEVICE=eth1
TYPE=Ethernet
ONBOOT=yes
BOOTPROTO=dhcp" > /etc/sysconfig/network-scripts/ifcfg-eth0
"""
        if release == "centos6":
            command = command6
        elif release == "redhat7":
            command = command7

        ret = self.sshcommand(server, username, password, command)

        return ret

    def shutdown(self, server, username, password):
        """shutdown the server"""
        command = "shutdown -h now"

        ret = self.sshcommand(server, username, password, command)

        return ret

    def sshcommand(self, server, username, password, command):
        """ssh in the server and execute command """
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            ssh.connect(server, username=username, password=password, timeout=5)
        except Exception as e:
            msg = "the server:%s use username:%s,password:%s connect faild" % (server, username, password)
            self.logfile.critical(msg)
            self.logfile.critical(e)
            return None

        try:
            _, stdout, stderr = ssh.exec_command(command)
        except Exception as e:
            msg = "execute command:%s faild" % command
            self.logfile.critical(e)
            return None
        finally:
            ssh.close()

        return True

    @staticmethod
    def checkRecord(vmname, method):
        """check the file is downloaded or upload"""
        fpath = ".vm/" + vmname + method
        ret = os.path.exists(fpath)

        return ret

    @staticmethod
    def writesuffix(logfile, fname, suffix):
        if not os.path.exists(".vm"):
            os.mkdir(".vm")

        open(".vm/" + fname + suffix, "a").close()


class base(object):
    """init the info of all compute, and get the token for access the api"""

    def __init__(self, logfile):
        confFile = sys.argv[1]

        headers = {}
        headers["Content-Type"] = "application/json"

        self.cf = ConfigParser()
        self.cf.read(confFile)
        self.conf = {k: v for k, v in self.cf.items("openstack")}
        self.headers = headers

        self.logfile = logfile
        self.catalog, self.token = self.getToken()

    def getURL(self, catalog, name):
        """
        get the public url of openstack services
        """
        url = [url for url in self.catalog if url["name"] == name]
        if url:
            url = url[0]["endpoints"][0]["publicURL"]

        return url

    def pre(self):
        """read the config file for init"""

        try:
            sec = self.cf.sections()
        except Exception as e:
            self.logfile.critical(e)
            self.logfile.critical("配置文件有误,没有配置[openstack],[vm],[vmware]段落")
            sys.exit(1)

        secLis = ['openstack', 'multiprocess', 'vm']
        openLis = ["auth_url", "uname", "passwd", "tenant"]
        vmLis = ["path"]

        testsec = [s for s in secLis if s in sec]
        if len(testsec) != 3:
            self.logfile.critical("配置文件有误,没有配置[openstack],[vm],[vmware]某一段落")
            sys.exit(1)

        for i in openLis:
            if i not in self.cf.options("openstack"):
                self.logfile.critical("配置文件有误,没有配置[openstack]段落,或缺少相关配置信息")
                sys.exit(1)

        for i in vmLis:
            if i not in self.cf.options("vm"):
                self.logfile.critical("配置文件有误,没有配置[vm]段落,或缺少相关配置信息")
                sys.exit(1)

        return True

    def getToken(self):
        headers = self.headers
        url = self.conf["auth_url"] + "/tokens"
        data = '{"auth": {"tenantName": "%s", "passwordCredentials": {"username": "%s", "password": "%s"}}}'
        data = data % (self.conf["tenant"], self.conf["uname"], self.conf["passwd"])

        try:
            msg = "Acquire token from %s " % self.conf["auth_url"]
            self.logfile.debug(msg)
            ret = requests.post(url, data=data, headers=headers)
            ret = ret.json()
        except Exception as e:
            msg = "Acuire Token failed \n data: %s \n headers: %s" % (data, headers)
            self.logfile.critical(msg)
            self.logfile.critical(e)

        catalog = ret["access"]["serviceCatalog"]
        token = ret["access"]["token"]["id"]

        return catalog, token

    def getResp(self, suffix, method, data=None, headers=None, params=None, isjson=True, api="nova"):
        """return the result of requests"""
        apiURL = self.getURL(self.catalog, api)
        url = apiURL + suffix
        if headers is None:
            headers = self.headers.copy()
        headers["X-Auth-Token"] = self.token

        req = getattr(requests, method)
        try:
            ret = req(url, data=data, headers=headers, params=params, verify=False)
            #print ret.url
            #print ret.content

            self.logfile.debug("request url:%s" % ret.url)
            if ret.status_code == 401:
                self.logfile.warning("Token expired, acquire token again")
                self.catalog, self.token = self.getToken()
                headers["X-Auth-Token"] = self.token
                self.logfile.debug("Request headers:%s" % ret.request.headers)
                ret = req(url, data=data, headers=headers)

            if isjson:
                retCode = ret.status_code
                if ret.content:
                    ret = ret.json()
                else:
                    ret = {}

                ret["status_code"] = retCode

        except Exception as e:
            msg = "The method:%s for path:%s failed \ndata:%s \nheaders:%s" % (method, suffix, data, headers)
            self.logfile.critical(msg)
            self.logfile.critical(e)
            sys.exit(1)
            ret = None

        return ret


class opCli(base):
    """the openstack rest api client """
    def __init__(self, logfile):
        super(opCli, self).__init__(logfile)

    def createImg(self, name, contf="bare", diskf="qcow2"):
        """create the img"""
        suffix = "/v2/images"

        data = {}
        data["container_format"] = contf
        data["disk_format"] = diskf
        data["name"] = name

        data = json.dumps(data)
        resp = self.getResp(suffix, "post", data=data, api="glance")

        return resp

    def uploadImg(self, imgPath, imgFile, vmname):
        """upload the image to openstack glance service"""
        suffix = imgPath
        headers = {'content-type': "application/octet-stream"}
        headers["X-Auth-Token"] = self.token
        apiURL = self.getURL(self.catalog, "glance")

        url = "".join([apiURL, suffix])

        try:
            msg = "Open the img: %s" % imgFile
            self.logfile.info(msg)
            with open(imgFile) as img:
                msg = "Put the img: %s" % imgPath
                self.logfile.info(msg)
                req = requests.put(url, headers=headers, data=img)
        except Exception as e:
            msg = "Open the img file failed"
            self.logfile.critical(msg)
            self.logfile.critical(e)
            return None

        if req.status_code == 204:
            ret = "ok"
            shex.writesuffix(self.logfile, vmname, ".upload")
            tmpret = shex.remove(imgFile)
            if tmpret:
                self.logfile.critical(tmpret)
        else:
            self.logfile.critical("UPload abnormally")
            self.logfile.critical(req.content)
            ret = req.content

        return ret

    def boot(self, name, imgRef, flavorRef, netRef):
        """boot the instance with specific img and network"""
        suffix = "/servers"
        server = {}
        data = {}
        server["name"] = name
        server["flavorRef"] = flavorRef
        server["imageRef"] = imgRef
        server["networks"] = []
        server["networks"].append({"uuid": netRef})
        data["server"] = server

        data = json.dumps(data)
        resp = self.getResp(suffix, "post", data=data)

        return resp

    def addFlotingIP(self, serID, ip):
        """add"""
        suffix = "/servers/%s/action" % serID
        data = {}
        data["addFloatingIp"] = {}
        data["addFloatingIp"]["address"] = ip

        data = json.dumps(data)
        resp = self.getResp(suffix, "post", data=data)

        return resp

    def listNet(self):
        """get the uuid"""
        suffix = "/v2.0/networks"

        resp = self.getResp(suffix, "get", api="neutron")

        return resp

    def listFlavor(self):
        """list the flavor"""
        suffix = "/flavors/detail"

        resp = self.getResp(suffix, "get")

        return resp

    def createFlavor(self, vmmem, vmcpu, vmdisk):
        """create the flavor"""
        suffix = "/flavors"
        name = "convert" + time.strftime("%Y-%m-%d-%H:%M")
        data = {}
        data["flavor"] = {}
        data["flavor"]["name"] = name
        data["flavor"]["ram"] = vmmem
        data["flavor"]["vcpus"] = vmcpu
        data["flavor"]["disk"] = vmdisk

        data = json.dumps(data)
        resp = self.getResp(suffix, "post", data=data)

        ret = resp["flavor"]["id"]

        return ret

    def getfixip(self, serID):
        """get the fixed ip of the server"""
        suffix = "/servers/" + serID

        resp = self.getResp(suffix, "get")

        if resp["status_code"] == 200:
            try:
                fixedip = resp["server"]["addresses"]["private"][0]["addr"]
            except Exception as e:
                self.logfile.critical("Get the fixed ip failed")
                self.logifle.critical(e)
        else:
            fixedip = None

        return fixedip


def download():
    """download the vmdk file and convert"""
    empty = qvm.empty()
    msg = "the vm of Queue empty is %s" % empty
    print msg
    while not qvm.empty():
        ret = False
        vm = qvm.get()
        logfile = InitLog(vm[7], console=True)
        logfile.info("===Download Process start===")
        logfile.info("get the infomation: %s" % vm)
        if shex.checkRecord(vm[7], ".wrong"):
            logfile.warning("The vm is wrong, skip this")
            continue

        try:
            vmrelease,vmuser,vmpass,vmip,exsiip,exsiuser,exsipass,vmname,vmmem,vmcpu,vmdisk,vmowner,vmproject,multidisk = vm
            vmowner = tryencode(vmowner)
            vmname = tryencode(vmname)
            #print vmrelease
        except Exception as e:
            msg = "The vm data is wrong: %s " % vm
            logfile.critical(msg)
            logfile.critical(e)
            shex.writesuffix(logfile, vmname, ".wrong")
            continue

        if shex.checkRecord(vm[7], ".wrong"):
            logfile.warning("The vm is wrong, skip this")
            continue

        shx = shex(exsiip, exsipass, vmname, logfile)
        downloaded = shx.checkRecord(vmname, ".download")
        msg = "Check if the vm have been downloaded: %s" % downloaded
        logfile.info(msg)
        if not downloaded:
            shx.poweroff(vmrelease, vmip, vmuser, vmpass)
            ret = shx.VirtDown()
            if not ret:
                msg = "Download faild ===> %s" % vm[7]
                logfile.info(msg)
                shex.writesuffix(logfile, vmname, ".wrong")
                continue

        if shex.checkRecord(vm[7], ".wrong"):
            logfile.warning("The vm is wrong, skip this")
            continue

        converted = shx.checkRecord(vmname, ".convert")
        msg = "Check if the vm have been converted: %s" % converted
        logfile.info(msg)
        if not shx.checkRecord(vmname, ".convert"):
            if vmrelease.lower() == "ubuntu":
                ret = shx.VirtConvert2()
            else:
                ret = shx.VirtConvert1()
        else:
            logfile.info("Converted")
            ret = True

        if ret:
            logfile.info("Put the converted vm to the queue for upload.....")
            qdown.put(vm)
            logfile.info("Put done...")
        else:
            logfile.critical("Converted failed!!!")
            shex.writesuffix(logfile, vmname, ".wrong")


def upload(bootimg=True):
    """upload the converted image and boot a server from the image"""
    empty = qdown.empty()
    msg = "upload vm of Queue empty is %s" % empty
    print msg
    while True:
        vm = qdown.get()

        logfile = InitLog(vm[7], console=True)
        logfile.info("===UPload Process start===")
        logfile.info("Get the infomation: %s" % vm)
        if shex.checkRecord(vm[7], ".wrong"):
            logfile.warning("The vm is wrong, skip this")
            continue

        try:
            vmrelease,vmuser,vmpass,vmip,exsiip,exsiuser,exsipass,vmname,vmmem,vmcpu,vmdisk,vmowner,vmproject,multidisk = vm
            vmowner = tryencode(vmowner)
            vmname = tryencode(vmname)
            vmmem = int(vmmem) * 1024
            vmcpu = int(vmcpu)
            vmdisk = int(vmdisk)
        except Exception as e:
            msg = "The vm data is wrong: %s " % vm
            logfile.critical(msg)
            logfile.critical(e)
            shex.writesuffix(logfile, vmname, ".wrong")
            continue

        op = opCli(logfile)
        imgfile = vmname + "-qcow2"
        msg = "Create the image from the vm file: %s" % vmname
        logfile.info(msg)

        if not shex.checkRecord(vmname, ".img"):
            img = op.createImg(vmname)
        else:
            if shex.checkRecord(vmname, ".upload"):
                logfile.info("image have been uploaded, skip this")
                continue
            else:
                imgdata = open(".vm/" + vmname + ".img")
                img = json.load(imgdata)

        #print img
        if img:
            msg = "The image create: %s" % vmname
            logfile.info(msg)
            shex.writesuffix(logfile, vmname, ".img")

            with open(".vm/" + vmname + ".img", "w") as rf:
                json.dump(img, rf)

            logfile.info("The image created")
        else:
            logfile.critical("Image create failed!!!")
            shex.writesuffix(logfile, vmname, ".wrong")
            continue

        imgPath = img["file"]
        imgID = img["id"]

        logfile.info("UPload image")
        uploaded = shex.checkRecord(vmname, ".upload")
        msg = "Check if the image uploaded: %s" % uploaded
        logfile.info(msg)

        if not shex.checkRecord(vmname, ".upload"):
            uploadRet = op.uploadImg(imgPath, imgfile, vmname)
        else:
            uploadRet = "uploaded"

        if uploadRet == "ok":
            logfile.info("UPload completed")
            shex.writesuffix(logfile, vmname, ".upload")
        elif uploadRet == "uploaded":
            logfile.info("Have been uploaded")
        else:
            logfile.critical("UPload failed")
            logfile.critical(uploadRet)
            shex.writesuffix(logfile, vmname, ".wrong")
            continue

        if not bootimg:
            logfile.info("Just download the image and upload...skip the action of boot")
            continue

        try:
            ext_vlan = "MC_VLAN_10.2." + vmip.split(".")[2]
            msg = "The floating ip network: %s" % ext_vlan
            logfile.info(msg)
            fix_vlan = op.cf.get(ext_vlan, "fix")
            msg = "The fixed ip network: %s" % fix_vlan
            logfile.info(msg)
        except Exception as e:
            logfile.critical("The network is invalid")
            logfile.error(e)
            logfile.critical("Network invail!!!")
            shex.writesuffix(logfile, vmname, ".wrong")
            continue

        networklis = op.listNet()["networks"]
        #print networklis

        network = [net["id"] for net in networklis if net["name"] == fix_vlan]

        if network:
            network = network[0]
            msg = "Get the fixed network: %s" % network
            logfile.info(msg)
        else:
            logfile.critical("Can't get the fixed network")
            shex.writesuffix(logfile, vmname, ".wrong")
            continue

        flavorlis = op.listFlavor()["flavors"]
        #print flavorlis
        #flavorlis4debug = [[f["id"], f["ram"], f["vcpus"], f["disk"]] for f in flavorlis]
        #print flavorlis4debug

        msg = "vm flavor: mem:: %s, cpu:: %s, disk:: %s" % (vmmem, vmcpu, vmdisk)
        logfile.info(msg)

        flavor = [[f["id"], f["ram"], f["vcpus"], f["disk"]] for f in flavorlis if f["ram"] >= vmmem and f["vcpus"] >= vmcpu and f["disk"] >= vmdisk]
        print flavor
        if len(flavor) > 1:
            flavor.sort(key=lambda x: x[3])
            flavor = flavor[0][0]
            msg = "There more than one flaors for select,so random select disk most mininal: %s" % flavor
            logfile.info(msg)

        elif len(flavor) == 0:
            logfile.info("There no suitable flavor for specify")
            msg = "Try create the flavor: mem:: %s, cpu:: %s, disk:: %s" % (vmmem, vmcpu, vmdisk)
            logfile.info(msg)
            flavor = op.createFlavor(vmmem, vmcpu, vmdisk)
        else:
            msg = "only one flavor for select: %s" % flavor
            logfile.info(msg)
            flavor = flavor[0][0]

        if flavor:
            logfile.info("Flavor selected succuess")
        else:
            logfile.critical("Flavor selected failed")
            logfile.critical("Exit.....")
            continue

        instance = "-".join([vmowner, vmname])
        msg = "Try to create the server: instanceName:: %s imgID:: %s network:: %s" % (instance, imgID, network)
        server = op.boot(instance, imgID, flavor, network)

        if server:
            if "server" in server:
                logfile.info("Boot the image success!!!")
            else:
                logfile.critical("Boot the image failed")
                shex.writesuffix(logfile, vmname, ".wrong")
                continue
        else:
            logfile.critical("Boot the image failed")
            shex.writesuffix(logfile, vmname, ".wrong")
            continue

        serverID = server["server"]["id"]
        msg = "Try to add floating ip to the instance: %s" % vmip
        time.sleep(3)
        floatingip = op.addFlotingIP(serverID, vmip)

        if floatingip:
            if floatingip["status_code"] == 202:
                logfile.info("Add floationgip success!!!")
            else:
                logfile.critical("Add floationgip failed")
                logfile.critical(floatingip)
                shex.writesuffix(logfile, vmname, ".wrong")
                continue
        else:
            logfile.critical("Add floationgip  failed")
            logfile.critical("HTTP failed maybe.....")
            shex.writesuffix(logfile, vmname, ".wrong")

    logfile.info("UPload process done......")


def batch(action, size, *args, **bootimg):
    """batch run the action for higher performance"""
    #print action,size,args
    p = Pool(size)
    for i in range(size):
        p.apply_async(action, kwds=bootimg)

    return p


def testvmware():
    log = InitLog("test.log", console=True)
    with open("test.csv") as rf:
        csvRead = csv.reader(rf)
        csvRet = [line for line in csvRead]
        retDict = {}
        retDict["release"] = csvRet[1][0]
        retDict["vmip"] = csvRet[1][3]
        retDict["exsi"] = csvRet[1][4]
        retDict["exsipass"] = csvRet[1][6]
        retDict["vmname"] = csvRet[1][7]
        retDict["owner"] = csvRet[1][12]
        retDict["group"] = csvRet[1][13]
        #retDict["mem"] = csvRet[1][14]
        #retDict["cpu"] = csvRet[1][15]

    print retDict
    sh = shex(retDict["exsi"], retDict["exsipass"], retDict["vmname"], log)
    #test vmdk file download
    sh.VirtDown()
    #test vmdk convert
    #sh.VirtConvert1()
    #sh.VirtConvert2()


def testopenstack():
    log = InitLog("test.log", console=True)
    #test opCli class initialize
    with open("test.csv") as rf:
       csvRead = csv.reader(rf)
       csvRet = [line for line in csvRead]
       retDict = {}
       retDict["release"] = csvRet[1][0]
       retDict["vmip"] = csvRet[1][3]
       retDict["exsi"] = csvRet[1][8]
       retDict["exsipass"] = csvRet[1][9]
       retDict["vmname"] = csvRet[1][11]
       retDict["owner"] = csvRet[1][12]
       retDict["group"] = csvRet[1][13]
       retDict["mem"] = csvRet[1][14]
       retDict["cpu"] = csvRet[1][15]

    op = opCli()
    #test img create
    #img = op.createImg("testvm")

    #get created image file path and id
    #imgfile = img["file"]
    #imgID = img["id"]

    #test upload img
    #print op.uploadImg(imgfile, "testvm.qcow2")


    #test boot server
    #server = op.boot("testvmfortest", imgID, "1", "541b6469-c0f9-4743-a756-66bcbc39d299")
    #serverID = server["server"]["id"]

    #test list Network and list Flavor
    pprint(op.listNet())
    pprint(op.listFlavor())


def testdownload():
    prelog = InitLog("testdownload")
    if len(sys.argv) < 2:
        prelog.critical("Have no sepecify the vm.conf")
        pre.critical("Exit....")
        sys.exit(1)

    op = opCli(prelog)
    csvformat = ['vmrelease','vmuser','vmpass','vmip','exsiip','exsiuser','exsipass','vmname','vmmem','vmcpu','vmdisk','vmowner','vmproject','multidisk']
    #print csvformat
    if not op.pre():
        pre.critical("The vm.conf configuration is wrong!!!!")
        pre.critical("Exit....")
        sys.exit(1)

    csvfile = op.cf.get("vm", "path")
    with open(csvfile) as rf:
        csvreader = csv.reader(rf)
        header = csvreader.next()
        #print header
        if header == csvformat:
            for line in csvreader:
                #print "====>line", line
                qvm.put(line)
                #print "====>empty", qvm.empty()
        else:
            prelog.critical("The format,header of vm is wrong!!!")
            pre.critical("Exit....")
            sys.exit(1)

    download()
    prelog.info("Download done....")


def testupload():
    prelog = InitLog("testupload")
    if len(sys.argv) < 2:
        prelog.critical("Have no sepecify the vm.conf")

    op = opCli(prelog)
    csvformat = ['vmrelease','vmuser','vmpass','vmip','exsiip','exsiuser','exsipass','vmname','vmmem','vmcpu','vmdisk','vmowner','vmproject','multidisk']
    #print csvformat
    if not op.pre():
        pre.critical("The vm.conf configuration is wrong!!!!")
        sys.exit(1)

    csvfile = op.cf.get("vm", "path")
    with open(csvfile) as rf:
        csvreader = csv.reader(rf)
        header = csvreader.next()
        #print header
        if header == csvformat:
            for line in csvreader:
                #print "====>line", line
                qdown.put(line)
                #print "====>empty", qvm.empty()
        else:
            prelog.critical("The format,header of vm is wrong!!!")
            pre.critical("Exit....")
            sys.exit(1)

    upload()
    prelog.info("UPload done....")


def main():
    prelog = InitLog("main")
    if len(sys.argv) < 2:
        prelog.critical("Have no sepecify the vm.conf")

    op = opCli(prelog)
    csvformat = ['vmrelease','vmuser','vmpass','vmip','exsiip','exsiuser','exsipass','vmname','vmmem','vmcpu','vmdisk','vmowner','vmproject','multidisk']
    #print csvformat
    if not op.pre():
        pre.critical("The vm.conf configuration is wrong!!!!")
        sys.exit(1)

    csvfile = op.cf.get("vm", "path")
    with open(csvfile) as rf:
        csvreader = csv.reader(rf)
        header = csvreader.next()
        #print header
        if header == csvformat:
            prelog.info("CSV format vaild")
            prelog.info("Put the vm infomation to queue....")
            for line in csvreader:
                qvm.put(line)
            prelog.info("Put done...")

        else:
            prelog.critical("The format,header of vm is wrong!!!")
            sys.exit(1)

    cf = ConfigParser()
    cf.read(sys.argv[1])

    try:
        prelog.info("Try to get the bootimg seeting")
        bootimg = cf.getboolean("openstack", "bootimg")
    except Exception as e:
        prelog.warning("Get the bootimg setting failed")
        prelog.warning("set the bootimg=True.....")
        bootimg = True

    downSize = cf.getint("multiprocess", "download")
    upSize = cf.getint("multiprocess", "upload")
    prelog.info("Start the download process...")
    downloadProc = batch(download, downSize)
    prelog.info("Start the upload process...")
    uploadProc = batch(upload, upSize, bootimg=bootimg)

    downloadProc.close()
    uploadProc.close()
    downloadProc.join()
    uploadProc.join()
    prelog.info("ALL done....")

if __name__ == "__main__":
   main()
   #testdownload()
   #testupload()
   #testvmware()
