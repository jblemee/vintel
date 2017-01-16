ROLLED THIS BACK FROM MainWindowUi, seems QWebEngineWidgets is not available in most PyQt5 builds

```
</widget>
<customwidgets>
 <customwidget>
  <class>QWebView</class>
  <class>QWebEngineView</class>
  <extends>QWidget</extends>
  <header>QtWebKit/QWebView</header>
  <header>PyQt5/QtWebEngineWidgets/QWebEngineView</header>
 </customwidget>
 <customwidget>
  <class>PanningWebView</class>
  <extends>QWebView</extends>
  <extends>QWebEngineView</extends>
  <header>vi/PanningWebView</header>
 </customwidget>
```
