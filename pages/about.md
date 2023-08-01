---
layout: page
title: About
description: 丰年留客 
keywords: Xue Che, 薛澈
comments: true
menu: 关于
permalink: /about/
---

linux内核爱好者，从事cgroup资源隔离及kata安全容器相关研发工作。

热衷于钻研底层技术，向往成为一个精通linux内核，掌握操作系统生态构建的技术专家。

## 联系

<ul>
{% for website in site.data.social %}
<li>{{website.sitename }}：<a href="{{ website.url }}" target="_blank">@{{ website.name }}</a></li>
{% endfor %}
</ul>


## Skill Keywords

{% for skill in site.data.skills %}
### {{ skill.name }}
<div class="btn-inline">
{% for keyword in skill.keywords %}
<button class="btn btn-outline" type="button">{{ keyword }}</button>
{% endfor %}
</div>
{% endfor %}
