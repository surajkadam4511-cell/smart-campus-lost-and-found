import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:file_selector/file_selector.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

void main() {
  runApp(const MaterialApp(
    debugShowCheckedModeBanner: false,
    home: CampusAppView(),
  ));
}

class CampusAppView extends StatefulWidget {
  const CampusAppView({super.key});

  @override
  State<CampusAppView> createState() => _CampusAppViewState();
}

class _CampusAppViewState extends State<CampusAppView> {
  late final WebViewController controller;
  bool isLoading = true;

@override
void initState() {
  super.initState();

  controller = WebViewController()
    ..setJavaScriptMode(JavaScriptMode.unrestricted)
    ..setNavigationDelegate(
      NavigationDelegate(
        onPageFinished: (String url) {
          setState(() {
            isLoading = false;
          });
        },
      ),
    );

  final androidController = controller.platform as AndroidWebViewController;

  androidController.setOnShowFileSelector((params) async {
    const imageTypes = <XTypeGroup>[
      XTypeGroup(
        label: 'images',
        extensions: <String>['jpg', 'jpeg', 'png', 'webp'],
      ),
    ];

    final file = await openFile(acceptedTypeGroups: imageTypes);

    if (file == null) {
      return <String>[];
    }

    return <String>[Uri.file(file.path).toString()];
  });

  controller.loadRequest(
    Uri.parse('https://campus-lost-and-found-gqge.onrender.com/login'),
  );
}

  @override
  Widget build(BuildContext context) {
    return WillPopScope(
      onWillPop: () async {
        if (await controller.canGoBack()) {
          controller.goBack();
          return false;
        }
        return true;
      },
      child: Scaffold(
        body: SafeArea(
          child: Stack(
            children: [
              WebViewWidget(controller: controller),
              if (isLoading)
                const Center(
                  child: CircularProgressIndicator(),
                ),
            ],
          ),
        ),
      ),
    );
  }
}