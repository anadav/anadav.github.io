---
layout: post
title:  "Can you break Windows Page Table Isolation?"
date:   2018-09-15 14:52:01 -0700
categories: Windows
redirect_from:
  - /blog/windows-pti
---


The Meltdown and L1TF attacks proved that Intel CPUs are susceptible for attacks that use speculative execution to leak data from the kernel address-space. The root-cause for both of these attacks is the ability of unprivileged code to read speculatively data even if the  page-table permissions should prevent the access. To address this security vulnerability Page Table Isolation (PTI) has been introduced by all common OSes. When PTI is used, a different set of page-tables is used when user-space run. 

The key for PTI to be effective is that it only allows an access to minimal set of privileged pages, whose content can be leaked. These pages include memory that holds various privileged architectural data-structures, for example the Global Descriptor Table (GDT), and privileged trampoline code. This trampoline code runs when a system call, interrupt or exception are invoked, and switches to the kernel page-table hierarchy, for the kernel to be able to handle this event.  

Is PTI implemented correctly? Well, in Linux, PTI implementation is open for review, reasonable, and is easy to audit . Microsoft provides a lot of information about the implementation of PTI in their system, but the code is obviously not open for review. Out of curiosity, I decided to check Windows 10. Using KVM and a  simple script, I dumped pages which are mapped as supervisor pages in the userspace. The results were surprising:

{% highlight bash %}
$ sudo ./pti_test.py --socket ~/vm-images/qmp-sock

kernel frames: 124
page tables accessible by the user: 0
page tables accessible by the kernel: 115
writable page tables: 115
page tables: 115
global kernel frames: 9
kernel w+x: 118
kernel/user aliases: 0
{% endhighlight %}

This results surprised me for two reasons. First, Windows 10 does not implement [W^X][wx], and maps pages which are both executable and writable even in the user page-tables. Inspecting the content of these pages shows that at least some of them are guaranteed not to hold code, and should have been marked as non-executable in the page-tables. I contacted Microsoft which claimed that this is intended since "in some cases the kernel is mapped with large pages" and that this can be prevented by enabling [virtualization based protection (VBS)][vbs]. However, dumping the page-tables (you can use the attached script), shows that no huge-pages were used, at least in my experiment, and still pages were mapped as writable and executable. VBS is not commonly used, and it might induce significant performance overheads, especially when Windows is being run inside a virtual-machine.

The second issue is that the page-tables themselves are mapped in the guest page-tables. Actually, Microsoft previously had a bug in which these page-tables could also be modified by userspace applications (in some Windows version). This obviously was a terrible [security vulnerability][windows-bug], since userspace applications could have established page-table entries that would allow them to access (read or write) any piece of memory. Today, they keep being mapped as writable, but only accessible by privileged code. Microsoft, again, claimed that this is necessary. I cannot understand why - Linux, for example, does not need to do so.

Can anyone exploit these behavior? Well, besides the fact that the lack of W^X ease fully compromising a system when another security vulnerability is found, Windows behavior might potentially enable more Meltdown-like attacks. As shown by the Meltdown and L1TF vulnerabilities, Intel CPUs defer at least some PTE validity and permission checks and still uses them during speculative execution. Mapping as few pages as possible in the userspace page-tables is necessary for good Meltdown mitigation as Microsoft itself [acknowledges][kva-shadow]. If one can somehow speculatively inject code or modify the page tables or the executable code, and use the modified versions, this would cause a security vulnerability.

Still, it is not clear whether it actually poses a security vulnerability. Initially, I thought that mapping the page-tables might be exploited by running a speculatively-executed code that sets page-table entries that grant userspace code access to privileged data, and then reads the data and leaks it. However, this is unlikely to work. Accessing data can only be done after the page-table entry is cached in the translation lookaside buffer (TLB), and the TLB should not be able to hold entries whose content is based on speculative execution. If TLB entries would have been set based on speculative execution results, this would cause correctness issues.

Feel free to use my silly script (through this [link][pti-script])  and let me know what you think. And if you are a security researcher, it might be worthy to have a look at Windows Spectre v2 mitigations. As I noted before, performance counters indicate that there are indirect branches inside Windows kernel, which might not be safe if Windows relies solely on retpolines for Spectre v2.

[wx]:          https://en.wikipedia.org/wiki/W%5EX
[vbs]:         https://docs.microsoft.com/en-us/windows/security/threat-protection/windows-defender-exploit-guard/enable-virtualization-based-protection-of-code-integrity
[windows-bug]: https://www.bleepingcomputer.com/news/microsoft/meltdown-patch-opened-bigger-security-hole-on-windows-7/
[kva-shadow]:  https://blogs.technet.microsoft.com/srd/2018/03/23/kva-shadow-mitigating-meltdown-on-windows/
[pti-script]:{{ site.baseurl }}/downloads/pti_test.py
