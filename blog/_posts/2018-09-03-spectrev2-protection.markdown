---
layout: post
title:  "Are you protected against Spectre & Meltdown? Probably not"
date:   2018-09-03 14:52:01 -0700
categories: Linux
---

Several months ago, everybody was surprised to find out that the CPU speculative execution can be exploited to leak privileged information, using attacks that were named Spectre and Meltdown. Technical blogs and even the main-stream media reported broadly about those vulnerabilities. CPU vendors have struggled to provide firmware patches that would prevent the attacks in a timely manner. OS and other software providers introduced software solutions such as the [retpoline][retpoline-man] and page table isolation (PTI) to protect against these vulnerabilities. All of these mitigations caused performance degradation, required extensive engineering effort, and caused various [problems][emergency-patch]. 

So half a year later - are you protected? Probably not. Recently I found that the Linux protection against Spectre v2 is broken in virtual machines and Dave Hansen found a bug in the [Meltdown][emergency-patch] protection. Spectre v1 was never considered fully resolved, with mitigations keep coming in, but even the existing ones were found to be [buggy][spectre-v1-patch-2]. 

There is clearly a problem, as currently it is hard for people to easily realize whether they are protected against these attacks. Sure, one can see whether the OS or other piece of software reports that it is protected, but these reports might be wrong. There is a fundamental problem with these protections that, in a way, is the same one that caused Linus Torvalds to politely (yes, politely) [decline][linus-decline] a Meltdown mitigation technique we proposed[^1]:

> Sure, I can see it working, but it's some really shady stuff, and now the scheduler needs to save/restore/check one more subtle bit.
>
> And if you get it wrong, things will happily work, except you've now defeated PTI. But you'll never notice, because you won't be testing for it, and the only people who will are the black hats.
>
> This is exactly the "security depends on it being in sync" thing that makes me go "eww" about the whole model. Get one thing wrong, and you'll blow all the PTI code out of the water.

Linus criticism of our work is valid, yet it does not seem that other protection mechanisms against these vulnerabilities are much better. And even if the OS is well-protected against these vulnerabilities, nobody guarantees that the system will remain safe after an out-of-tree module is loaded, for example. All it takes for the Spectre v2 protection to be broken, for example, is a single indirect branch that was not converted into a retpoline.  

It seems that in order to make the protection work, independent tools that validate the protection mechanisms are needed. I found the Spectre v2 by using the hardware performance counters to count indirect branches that were executed by the kernel and finding it is not zero. Dumping the page-tables and tracing translation-lookaside buffer (TLB) invalidations can be used to find out PTI bugs. Anti-malware tools should take up the glove and make these checks.

Yet, perhaps there is an additional problem of over-hyping Spectre. Side-channel attacks were known long before Spectre, and invoking them using speculative execution may not be such a game-changer. Unlike Meltdown, which is a real CPU bug, the Spectre family of vulnerabilities may pose lower risk as they are not easily exploitable. The Spectre v2 proof-of-concept exploited some Linux wrongdoings (e.g., not zeroing registers after a context switch from a virtual machine), which were relatively easily fixed and became a good mitigation against other OS bugs. Some new Spectre attacks were not even reported to be successfully exploitable other than in artificial [demos][spectre-v4].

It might be that the industry over-reacted to Spectre. Even if Spectre vulnerabilities are addressed, software might still leak privileged data through side-channels, so it is not as if the existing protection schemes are complete. Now that the media frenzy is gone, perhaps it is time to reconsider whether paying in performance for questionable "generic" protection schemes against these attacks makes sense, or whether protection should be done on a case-by-case basis.

Update: I wonder if Windows is indeed safe. Windows uses retpoline, but it is not clear whether they are used exclusively or with alternative solutions that use hardware mitigation (IBPB/IBRS). Anyhow, measuring the performance counter of Windows 10 (that runs in the VM) raises some questions, as it show there are indirect branches inside Windows kernel. Here are the performance counters as measure in a KVM guest:

{% highlight bash %}
$ sudo perf stat -e br_inst_exec.taken_indirect_jump_non_call_ret:Gk \
  -e br_inst_exec.taken_indirect_near_call:Gk -a -- sleep 5
 
 Performance counter stats for 'system wide':

         1,682,939      br_inst_exec.taken_indirect_jump_non_call_ret:Gk
         1,102,037      br_inst_exec.taken_indirect_near_call:Gk

       5.001077704 seconds time elapsed
{% endhighlight %}

[^1]: Based on work with Michael Wei and Dan Tsafrir (who may not share my views)


[emergency-patch]:	https://www.darkreading.com/risk/microsoft-issues-emergency-patch-to-disable-intels-broken-spectre-fix/d/d-id/1330932
[meltdown-patch]:	https://git.kernel.org/pub/scm/linux/kernel/git/tip/tip.git/commit/?h=x86/pti-urgent&id=c40a56a7818cfe735fc93a69e1875f8bba834483
[retpoline-man]:	https://software.intel.com/security-software-guidance/api-app/sites/default/files/Retpoline-A-Branch-Target-Injection-Mitigation.pdf
[spectre-v1-patch-1]:	https://git.kernel.org/pub/scm/linux/kernel/git/tip/tip.git/commit/?h=x86/pti-urgent&id=bc5b6c0b62b932626a135f516a41838c510c6eba
[spectre-v1-patch-2]:	https://www.spinics.net/lists/linux-tip-commits/msg44433.html
[spectre-v2-patch]:	https://git.kernel.org/pub/scm/linux/kernel/git/tip/tip.git/commit/?id=5800dc5c19f34e6e03b5adab1282535cb102fafd
[linus-decline]:	https://lkml.org/lkml/2018/2/15/1378
[spectre-v4]:		https://bugs.chromium.org/p/project-zero/issues/detail?id=1528
