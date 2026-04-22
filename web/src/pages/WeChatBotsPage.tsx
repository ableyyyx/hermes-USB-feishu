import { useEffect, useState } from "react";
import { MessageSquare, Plus, Trash2, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import type { WeChatBot, WeChatQRPoll } from "@/lib/api";
import { useToast } from "@/hooks/useToast";
import { Toast } from "@/components/Toast";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function WeChatBotsPage() {
  const [bots, setBots] = useState<WeChatBot[]>([]);
  const [loading, setLoading] = useState(true);
  const [showQRDialog, setShowQRDialog] = useState(false);
  const [qrSession, setQRSession] = useState<(WeChatQRPoll & { shareUrl?: string }) | null>(null);
  const { toast, showToast } = useToast();

  const loadBots = () => {
    setLoading(true);
    api
      .listWeChatBots()
      .then((resp) => setBots(resp.bots))
      .catch(() => showToast("Failed to load WeChat bots", "error"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadBots();
  }, []);

  const handleAddBot = async () => {
    try {
      const resp = await api.startWeChatQR();
      setShowQRDialog(true);
      setQRSession({ status: "starting", qr_data: null, account_id: null });

      // Generate shareable link
      const shareUrl = `${window.location.origin}/qr/${resp.session_id}`;
      setQRSession(prev => prev ? { ...prev, shareUrl } : null);

      // Start polling
      pollQRStatus(resp.session_id);
    } catch (err) {
      showToast("Failed to start QR login", "error");
    }
  };

  const pollQRStatus = async (sid: string) => {
    try {
      const status = await api.pollWeChatQR(sid);
      // Preserve shareUrl when updating status
      setQRSession(prev => prev ? { ...status, shareUrl: prev.shareUrl } : status);

      if (status.status === "confirmed") {
        showToast("WeChat bot added successfully!", "success");
        setTimeout(() => {
          setShowQRDialog(false);
          loadBots();
        }, 2000);
      } else if (status.status === "expired") {
        showToast("QR code expired", "error");
      } else if (status.status === "error") {
        showToast(status.error || "QR login failed", "error");
      } else {
        // Continue polling for other statuses (starting, wait, scaned)
        setTimeout(() => pollQRStatus(sid), 2000);
      }
    } catch (err) {
      showToast("Failed to poll QR status", "error");
    }
  };

  const handleDeleteBot = async (accountId: string) => {
    if (!confirm(`确定要删除机器人 ${accountId} 吗？这将删除所有相关数据。`)) {
      return;
    }
    try {
      await api.deleteWeChatBot(accountId);
      showToast("Bot deleted successfully", "success");
      loadBots();
    } catch (err) {
      showToast("Failed to delete bot", "error");
    }
  };

  const closeQRDialog = () => {
    setShowQRDialog(false);
    setQRSession(null);
  };

  const STATUS_DISPLAY: Record<string, { text: string; color: string }> = {
    starting: { text: "正在生成二维码...", color: "text-blue-600" },
    wait: { text: "请用微信扫码", color: "text-green-600" },
    scaned: { text: "已扫码，请在微信中确认...", color: "text-yellow-600" },
    confirmed: { text: "绑定成功！", color: "text-green-600" },
    expired: { text: "二维码已过期", color: "text-red-600" },
    error: { text: "登录失败", color: "text-red-600" },
  };

  return (
    <div className="space-y-6">
      <Toast toast={toast} />

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">WeChat Bots</h1>
          <p className="text-sm text-muted-foreground mt-1">
            管理微信机器人账号
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={loadBots}>
            <RefreshCw className="h-4 w-4 mr-2" />
            刷新
          </Button>
          <Button onClick={handleAddBot}>
            <Plus className="h-4 w-4 mr-2" />
            添加机器人
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      ) : bots.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <MessageSquare className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-muted-foreground">暂无微信机器人</p>
            <p className="text-sm text-muted-foreground mt-1">
              点击"添加机器人"按钮开始
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>已添加的机器人 ({bots.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {bots.map((bot) => (
                <div
                  key={bot.account_id}
                  className="flex items-center justify-between p-4 border rounded-lg hover:bg-accent/50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <MessageSquare className="h-5 w-5 text-green-600" />
                    <div>
                      <div className="font-medium">{bot.account_id}</div>
                      {bot.user_id && (
                        <div className="text-sm text-muted-foreground">
                          User ID: {bot.user_id}
                        </div>
                      )}
                      <div className="text-xs text-muted-foreground mt-1">
                        {bot.profile_dir}
                      </div>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDeleteBot(bot.account_id)}
                  >
                    <Trash2 className="h-4 w-4 text-red-600" />
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* QR Code Dialog */}
      {showQRDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md mx-4">
            <CardHeader>
              <CardTitle>添加微信机器人</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {qrSession && (
                <>
                  <div className="text-center">
                    <p
                      className={`text-lg font-medium ${
                        STATUS_DISPLAY[qrSession.status]?.color || ""
                      }`}
                    >
                      {STATUS_DISPLAY[qrSession.status]?.text || qrSession.status}
                    </p>
                  </div>

                  {qrSession.status === "starting" && (
                    <div className="flex justify-center py-8">
                      <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
                    </div>
                  )}

                  {qrSession.status === "wait" && qrSession.qr_data && (
                    <div className="flex flex-col items-center space-y-4">
                      <img
                        src={qrSession.qr_data}
                        alt="WeChat QR Code"
                        className="w-64 h-64 border-2 border-gray-300 rounded-lg"
                      />
                      <p className="text-sm text-muted-foreground">
                        使用微信扫描上方二维码
                      </p>

                      {qrSession.shareUrl && (
                        <div className="w-full mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                          <p className="text-sm font-medium text-blue-900 mb-2">
                            📤 分享链接给用户
                          </p>
                          <div className="flex items-center gap-2">
                            <input
                              type="text"
                              value={qrSession.shareUrl}
                              readOnly
                              className="flex-1 px-3 py-2 text-sm bg-white border border-blue-300 rounded"
                              onClick={(e) => (e.target as HTMLInputElement).select()}
                            />
                            <Button
                              size="sm"
                              onClick={() => {
                                navigator.clipboard.writeText(qrSession.shareUrl!);
                                showToast("链接已复制", "success");
                              }}
                            >
                              复制
                            </Button>
                          </div>
                          <p className="text-xs text-blue-700 mt-2">
                            用户访问此链接即可扫码绑定，无需登录 Dashboard
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {qrSession.status === "scaned" && (
                    <div className="flex justify-center py-8">
                      <div className="h-8 w-8 animate-spin rounded-full border-4 border-yellow-500 border-t-transparent" />
                    </div>
                  )}

                  {qrSession.status === "confirmed" && qrSession.account_id && (
                    <div className="text-center space-y-2">
                      <div className="text-green-600 text-4xl">✓</div>
                      <p className="text-sm text-muted-foreground">
                        Account ID: {qrSession.account_id}
                      </p>
                    </div>
                  )}

                  {qrSession.status === "expired" && (
                    <div className="text-center space-y-4">
                      <p className="text-sm text-muted-foreground">
                        二维码已过期，请重新添加
                      </p>
                      <Button onClick={handleAddBot} variant="outline">
                        重新生成
                      </Button>
                    </div>
                  )}

                  {qrSession.status === "error" && (
                    <div className="text-center space-y-2">
                      <p className="text-sm text-red-600">
                        {qrSession.error || "未知错误"}
                      </p>
                    </div>
                  )}
                </>
              )}

              <div className="flex justify-end gap-2 pt-4 border-t">
                <Button
                  variant="outline"
                  onClick={closeQRDialog}
                  disabled={qrSession?.status === "starting"}
                >
                  {qrSession?.status === "confirmed" ? "完成" : "取消"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
