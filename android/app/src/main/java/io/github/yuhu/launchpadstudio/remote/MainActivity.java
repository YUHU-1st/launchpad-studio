package io.github.yuhu.launchpadstudio.remote;

import android.app.Activity;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

public class MainActivity extends Activity {
    private static final int BG = Color.rgb(11, 13, 18);
    private static final int PANEL = Color.rgb(20, 25, 35);
    private static final int TEXT = Color.rgb(243, 245, 251);
    private static final int MUTED = Color.rgb(141, 151, 173);
    private static final int ACCENT = Color.rgb(124, 92, 255);

    private WebView webView;
    private LinearLayout connectionPanel;
    private EditText addressInput;
    private EditText pinInput;
    private TextView connectionStatus;
    private SharedPreferences prefs;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        prefs = getSharedPreferences("launchpad_remote", MODE_PRIVATE);
        setContentView(buildUi());
        String savedAddress = prefs.getString("address", "");
        String savedPin = prefs.getString("pin", "");
        String intentAddress = getIntent().getStringExtra("address");
        String intentPin = getIntent().getStringExtra("pin");
        if (intentAddress != null && !intentAddress.isEmpty()) savedAddress = intentAddress;
        if (intentPin != null && !intentPin.isEmpty()) savedPin = intentPin;
        addressInput.setText(savedAddress);
        pinInput.setText(savedPin);
        if (!savedAddress.isEmpty() && savedPin.length() == 6) connect(savedAddress, savedPin);
    }

    private View buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(BG);

        LinearLayout bar = new LinearLayout(this);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setPadding(dp(16), dp(10), dp(10), dp(10));
        bar.setBackgroundColor(BG);
        TextView title = text("Launchpad Studio 2 · Matrix Remote", 17, TEXT);
        bar.addView(title, new LinearLayout.LayoutParams(0, dp(46), 1));
        Button settings = button("连接设置", false);
        settings.setOnClickListener(v -> showConnectionPanel(""));
        bar.addView(settings, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(42)));
        root.addView(bar, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(62)));

        FrameLayout content = new FrameLayout(this);
        if ((getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0) WebView.setWebContentsDebuggingEnabled(true);
        webView = new WebView(this);
        webView.setBackgroundColor(BG);
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.getSettings().setAllowFileAccess(false);
        webView.getSettings().setMediaPlaybackRequiresUserGesture(false);
        webView.setWebViewClient(new WebViewClient() {
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) showConnectionPanel("无法连接电脑，请检查地址、Wi-Fi 和桌面遥控服务。");
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, android.webkit.WebResourceResponse response) {
                if (request.isForMainFrame() && response.getStatusCode() >= 400) showConnectionPanel("电脑拒绝连接，请检查配对 PIN。");
            }
        });
        content.addView(webView, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        connectionPanel = buildConnectionPanel();
        content.addView(connectionPanel, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        root.addView(content, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        return root;
    }

    private LinearLayout buildConnectionPanel() {
        LinearLayout outer = new LinearLayout(this);
        outer.setGravity(Gravity.CENTER);
        outer.setBackgroundColor(BG);
        outer.setPadding(dp(22), dp(22), dp(22), dp(22));
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(20), dp(20), dp(20), dp(20));
        card.setBackgroundColor(PANEL);
        TextView heading = text("连接电脑", 23, TEXT);
        card.addView(heading);
        TextView help = text("在电脑端 Launchpad Studio 点击“手机遥控”，把显示的局域网地址和 6 位 PIN 填到这里。", 14, MUTED);
        help.setPadding(0, dp(8), 0, dp(16));
        card.addView(help);
        addressInput = edit("电脑地址，例如 http://192.168.1.10:8765", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        card.addView(addressInput, match(dp(52), dp(8)));
        pinInput = edit("6 位配对 PIN", InputType.TYPE_CLASS_NUMBER);
        pinInput.setMaxLines(1);
        card.addView(pinInput, match(dp(52), dp(8)));
        Button connect = button("连接 Launchpad Studio", true);
        connect.setOnClickListener(v -> connect(addressInput.getText().toString(), pinInput.getText().toString()));
        card.addView(connect, match(dp(52), dp(12)));
        connectionStatus = text("手机和电脑需要连接同一局域网。", 13, MUTED);
        card.addView(connectionStatus);
        outer.addView(card, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return outer;
    }

    private void connect(String rawAddress, String rawPin) {
        String address = normalizeAddress(rawAddress);
        String pin = rawPin.trim();
        if (address.isEmpty()) { showConnectionPanel("请输入电脑地址。"); return; }
        if (!pin.matches("\\d{6}")) { showConnectionPanel("配对 PIN 应为 6 位数字。"); return; }
        prefs.edit().putString("address", address).putString("pin", pin).apply();
        addressInput.setText(address); pinInput.setText(pin);
        connectionStatus.setText("正在连接…");
        connectionPanel.setVisibility(View.GONE);
        String encoded = pin;
        webView.loadUrl(address + "/?token=" + encoded);
    }

    private String normalizeAddress(String raw) {
        String value = raw == null ? "" : raw.trim();
        if (value.isEmpty()) return "";
        if (!value.startsWith("http://") && !value.startsWith("https://")) value = "http://" + value;
        while (value.endsWith("/")) value = value.substring(0, value.length() - 1);
        return value;
    }

    private void showConnectionPanel(String message) {
        connectionPanel.setVisibility(View.VISIBLE);
        if (connectionStatus != null && message != null && !message.isEmpty()) connectionStatus.setText(message);
    }

    private EditText edit(String hint, int inputType) {
        EditText input = new EditText(this);
        input.setHint(hint); input.setHintTextColor(MUTED); input.setTextColor(TEXT); input.setSingleLine(true);
        input.setInputType(inputType); input.setPadding(dp(12), 0, dp(12), 0); input.setBackgroundColor(Color.rgb(27,33,48));
        return input;
    }

    private Button button(String label, boolean primary) {
        Button button = new Button(this); button.setText(label); button.setTextColor(TEXT); button.setAllCaps(false);
        button.setBackgroundColor(primary ? ACCENT : Color.rgb(27,33,48)); return button;
    }

    private TextView text(String value, int size, int color) {
        TextView text = new TextView(this); text.setText(value); text.setTextSize(size); text.setTextColor(color); return text;
    }

    private LinearLayout.LayoutParams match(int height, int topMargin) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, height); params.topMargin = topMargin; return params;
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    @Override
    public void onBackPressed() {
        if (connectionPanel.getVisibility() == View.VISIBLE) { connectionPanel.setVisibility(View.GONE); return; }
        if (webView.canGoBack()) { webView.goBack(); return; }
        showConnectionPanel("");
    }
}
