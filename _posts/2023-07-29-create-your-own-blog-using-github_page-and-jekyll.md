---
layout: post
title: 使用github page + jekyll 搭建免费的博客网站
categories: [教程]
description: 如何使用github page和jekyll快速搭建出一个属于自己的博客
keywords: github page, jekyll, 搭建个人博客
mermaid: false
sequence: false
flow: false
mathjax: false
mindmap: false
mindmap2: false
---

## 背景

&emsp;&emsp;当大家能搜到这篇文章时，想必大家应该和我的想法一样，亲自动手用github page和jekyll来搭建自己的博客，是一件比较cool的事情。我一直想尝试着写博客，把工作中的技术积累或者是生活中的所见所闻记录下来，但万事开头难，迟迟没有开始做这件事。今天就以这样一篇教程类文章作为自己的第一篇博客。OK，话不多说，进入正文。

## jekyll + github page的工作原理

&emsp;&emsp;[Jekyll](https://jekyllrb.com)是一个静态站点生成器。可以简单的理解成，我们可以使用Markdown来写文章，使用HTML文件来定制我们博客网站的外观，剩下的交给jekyll,由它自动为我们生成博客网站。
  
&emsp;&emsp;[Github pages](https://docs.github.com/en/pages/getting-started-with-github-pages/about-github-pages)是一种静态站点托管服务。可以简单的理解成，它就是一个后端服务器，为我们托管了一个github.io的网站，我们可以向这个github仓库提交CSS、HTML和JavaScript文件，然后jekyll根据这些文件构建出网站，通过类似github.io的域名供外界用户访问。
   
&emsp;&emsp;由此可见，我们首先需要创建一个github仓库并对github page配置一些相关参数；然后向新建的github 仓库中提交一些文件供jekyll来解析构建网站；最后就可以使用markdown语法来写文章并提交到github仓库中即可。

## 搭建博客的方法

### 创建github.io仓库并配置github page

&emsp;&emsp;首先需要创建一个名称为username.github.io的仓库，其中username是你的github账户名。然后进入到Settings->Pages选项下，可以看到一个默认生成的https://username.github.io网站，可以将网站域名修改成自定义的域名；此外，可以选择添加jekyll的官方网站主题。如下图：
![Github pages setting](/images/posts/jiaocheng/github_pages_setting.png)

&emsp;&emsp;这里我们暂时不进行自定义网站域名，也不使用官方提供的jekyll主题。可以直接向仓库中提交一个index.html的文件，如下,然后访问https://username.github.io网站，确认是否可以看到正确的测试文本。
```
echo "Welcome to my blog!" >> index.html
git add --all
git commit -m "test github page"
git push -u origin main
```

&emsp;&emsp;当上述测试访问成功后，接下来我们就需要找一个我们喜欢的jekyll主题，然后提交到username.github.io仓库中。


### 选择一个你中意的jekyll 网站主题

&emsp;&emsp;对于不太熟悉前端语言的同学，可以直接去某度上下载自己中意的jekyll主题。当然，不排除大佬们完全可以自行设计自己的博客外观。我是完全参考这个[jekyll主题](https://github.com/mzlogin/mzlogin.github.io)来搞的。按照其中的“Fork指南”操作即可，修改完后如下：

![My blog look](/images/posts/jiaocheng/my_blog_look.png)

&emsp;&emsp;当然，网上有各种各样的jekyll主题，可以参考[这篇博客](https://blog.csdn.net/chen_z_p/article/details/103132625)的汇总结果。


### 写下你的第一篇博客并在本地预览

&emsp;&emsp;到现在为止，准备工作基本已经做完了。你就可以在\_post目录下以"年-月-日-tile.md"格式命名来写下自己的第一篇博客。当然，你需要使用markdown语法来写啦，如果你不熟悉markdown语法，那也没关系，完全可以照葫芦画瓢，无非就是如何设置标题、如何插入链接、如何插入图片，这些基本的语法很快就能掌握，其他高级语法完全可以有需求的时候再去百度就可以了。

&emsp;&emsp;到这里，就会遇到一个比较头疼的问题，只有将博客提交到github.io仓库后，我们才能看到最终在网站上的显示效果。如何才能实现本地预览呢?此时就需要在本地安装jekyll编译环境了，利用jekyll实现本地预览，方便我们边写文章边调试。

&emsp;&emsp;我的本地环境是Mac，其安装过程主要如下：<br />
1. 安装rubygems<br />
```
$ brew install ruby
```
2. 安装jekyll<br />
```
$ sudo gem install jekyll
$ sudo gem install jekyll bundler
```
3. 安装bundle<br />
```
$ sudo bundle install
```
4. 开启本地预览<br />
```
$ cd {本地github.io仓库} 
$ bundle exec jekyll serve
```
&emsp;&emsp;jekyll server成功启动后，如下图, 输入“Server Address”对应的地址即可本地实时访问博客。

![Jekyll server](/images/posts/jiaocheng/jekyll_server.png)

&emsp;&emsp;其中，安装jekyll编译环境耗费了我比较大的精力，主要是因为遇到了一些奇奇怪怪的问题，例如:<br /> 
* homerew和gem的下载速度超级慢，通过替换相应的源来解决
* rubby和jekyll的版本不兼容问题，根据提示升级rubby版本即可
* gem install jekyll时出现编译报错<br /> 

每个人的本地环境不同，这些问题可能不一定都会遇到，我这里把遇到的一些问题及解决方法贴出来（ps:链接在后文「参考」章节），供大家参考。

&emsp;&emsp; Ok，感谢读者能够耐心读完这篇文章，如有不当之处，不吝赐教。

## 参考
[使用Jekyll和GitHub Pages搭建博客原理、方法和资源](http://www.hackermi.com/2015-02/build-github-blog-manual/)<br />
[用Github pages 和 Jekyll 搭建博客](https://yuleii.github.io/2020/06/09/build-blog-with-github-pages-and-jekyll.html)<br />
[记录一个Homebrew无法安装软件的问题](https://zhuanlan.zhihu.com/p/604160866)<br />
[Ruby Gems 镜像使用帮助](https://mirrors.tuna.tsinghua.edu.cn/help/rubygems/)<br />
[解决sudo xcrun gem install cocoapods 时报错 ‘ruby/config.h‘ file not found](https://blog.csdn.net/Baby_come_here/article/details/125144329)<br />
[安装Ruby On Rails时运行“gem install rails”没有反应怎么办？](https://blog.csdn.net/keyboardOTA/article/details/8897798?spm=1001.2101.3001.6650.16&utm_medium=distribute.pc_relevant.none-task-blog-2%7Edefault%7EBlogCommendFromBaidu%7ERate-16-8897798-blog-105998061.235%5Ev38%5Epc_relevant_default_base3&depth_1-utm_source=distribute.pc_relevant.none-task-blog-2%7Edefault%7EBlogCommendFromBaidu%7ERate-16-8897798-blog-105998061.235%5Ev38%5Epc_relevant_default_base3&utm_relevant_index=22)<br />
