#include "selfdrive/ui/qt/onroad/buttons.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QMap>
#include <QPainter>

#include "selfdrive/ui/qt/util.h"
#include "selfdrive/ui/qt/widgets/input.h"

void drawIcon(QPainter &p, const QPoint &center, const QPixmap &img, const QBrush &bg, float opacity) {
  p.setRenderHint(QPainter::Antialiasing);
  p.setOpacity(1.0);  // bg dictates opacity of ellipse
  p.setPen(Qt::NoPen);
  p.setBrush(bg);
  p.drawEllipse(center, btn_size / 2, btn_size / 2);
  p.setOpacity(opacity);
  p.drawPixmap(center - QPoint(img.width() / 2, img.height() / 2), img);
  p.setOpacity(1.0);
}

// ExperimentalButton
ExperimentalButton::ExperimentalButton(QWidget *parent) : experimental_mode(false), engageable(false), QPushButton(parent) {
  setFixedSize(btn_size, btn_size);

  engage_img = loadPixmap("../assets/img_chffr_wheel.png", {img_size, img_size});
  experimental_img = loadPixmap("../assets/img_experimental.svg", {img_size, img_size});
  QObject::connect(this, &QPushButton::clicked, this, [this]() {
    if (long_press_fired) {
      long_press_fired = false;  // the press opened the theme picker; don't also toggle Experimental Mode
      return;
    }
    changeMode();
  });

  // FrogPilot variables
  QObject::connect(frogpilotUIState(), &FrogPilotUIState::themeUpdated, this, &ExperimentalButton::updateTheme);

  // Keith: hold the wheel for 0.8 s while parked to pick a theme
  long_press_timer = new QTimer(this);
  long_press_timer->setSingleShot(true);
  long_press_timer->setInterval(800);
  QObject::connect(long_press_timer, &QTimer::timeout, this, [this]() {
    long_press_fired = true;
    showThemePicker();
  });
  QObject::connect(this, &QPushButton::pressed, this, [this]() {
    long_press_fired = false;
    if (parked) {
      long_press_timer->start();
    }
  });
  QObject::connect(this, &QPushButton::released, long_press_timer, &QTimer::stop);
}

static QString themeDisplayName(const QString &key) {
  QString base = key;
  base.remove("-user_created");
  bool animated = base.endsWith("-animated");
  base.remove("-animated");
  QString creator;
  int tilde = base.indexOf('~');
  if (tilde >= 0) {
    creator = base.mid(tilde + 1);
    base = base.left(tilde);
  }
  QStringList words;
  for (const QString &word : base.split('_')) {   // no SkipEmptyParts: deprecated in newer Qt and the build uses -Werror
    if (!word.isEmpty()) words << word.left(1).toUpper() + word.mid(1);
  }
  QString name = words.join(' ');
  if (animated) name += " (animated)";
  if (!creator.isEmpty()) name += " by " + creator;
  return name;
}

void ExperimentalButton::showThemePicker() {
  // Same rule as ThemeManager.get_full_themes(): colors and sounds, plus icons (own or the "-animated" twin)
  const QString packs = "/data/themes/theme_packs";
  QDir dir(packs);
  QMap<QString, QString> keyForName;
  for (const QString &entry : dir.entryList(QDir::Dirs | QDir::NoDotAndDotDot, QDir::Name)) {
    QString base = QString(entry).remove("-animated");
    bool full = QDir(packs + "/" + base + "/colors").exists() && QDir(packs + "/" + base + "/sounds").exists();
    bool animatedIcons = QDir(packs + "/" + base + "-animated/icons").exists();
    bool baseIcons = QDir(packs + "/" + base + "/icons").exists();
    if (!full || !(animatedIcons || baseIcons)) continue;
    QString key = animatedIcons ? base + "-animated" : base;
    keyForName.insert(themeDisplayName(key), key);
  }
  if (keyForName.isEmpty()) return;

  QString currentKey = QFileInfo(QFileInfo("../../frogpilot/assets/active_theme/icons").symLinkTarget()).dir().dirName();
  QString current = keyForName.key(currentKey);

  QString selection = MultiOptionDialog::getSelection(tr("Pick a theme"), keyForName.keys(), current, window());
  if (selection.isEmpty() || !keyForName.contains(selection)) return;

  // frogpilot_process switches everything (colors, icons, sounds, signals, wheel) when it sees this file
  QFile request("/dev/shm/keith_theme_request.tmp");
  if (request.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
    request.write(keyForName.value(selection).toUtf8());
    request.close();
    QFile::remove("/dev/shm/keith_theme_request");
    QFile::rename("/dev/shm/keith_theme_request.tmp", "/dev/shm/keith_theme_request");
  }
}

void ExperimentalButton::showEvent(QShowEvent *event) {
  updateTheme();
}

void ExperimentalButton::hideEvent(QHideEvent *event) {
  wheel_gif.reset();

  QPushButton::hideEvent(event);
}

void ExperimentalButton::updateTheme() {
  if (isVisible()) {
    loadImage("../../frogpilot/assets/active_theme/steering_wheel/wheel", wheel_img, wheel_gif, QSize(img_size, img_size), this);
  } else {
    wheel_gif.reset();
  }

  const QString wheel_source = QFileInfo("../../frogpilot/assets/active_theme/steering_wheel/wheel.png").canonicalFilePath();
  const QString stock_source = QFileInfo("../../frogpilot/assets/stock_theme/steering_wheel/wheel.png").canonicalFilePath();
  wheel_is_stock = wheel_source == stock_source;
}

void ExperimentalButton::changeMode() {
  const auto cp = (*uiState()->sm)["carParams"].getCarParams();
  bool can_change = hasLongitudinalControl(cp) && params.getBool("ExperimentalModeConfirmed");
  if (can_change) {
    // FrogPilot variables
    const QJsonObject &frogpilot_toggles = frogpilotUIState()->frogpilot_toggles;

    if (frogpilot_toggles.value("conditional_experimental_mode").toBool() || frogpilot_toggles.value("slc_fallback_experimental_mode").toBool()) {
      frogpilotUIState()->experimentalModePressed();
    } else {
      params.putBool("ExperimentalMode", !experimental_mode);
    }
  }
}

void ExperimentalButton::updateState(const UIState &s, const FrogPilotUIState &fs, const QJsonObject &frogpilot_toggles) {
  const auto cs = (*s.sm)["controlsState"].getControlsState();
  bool eng = cs.getEngageable() || cs.getEnabled() || fs.frogpilot_scene.always_on_lateral_active;
  if ((cs.getExperimentalMode() != experimental_mode) || (eng != engageable)) {
    engageable = eng;
    experimental_mode = cs.getExperimentalMode();
    update();
  }

  // FrogPilot variables
  const cereal::CarState::Reader &carState = (*s.sm)["carState"].getCarState();

  parked = (*fs.sm)["frogpilotCarState"].getFrogpilotCarState().getParked() && carState.getStandstill();
  if (!parked) {
    long_press_timer->stop();
  }

  int steering_angle = frogpilot_toggles.value(QLatin1String("rotating_wheel")).toBool() ? -carState.getSteeringAngleDeg() : 0;
  QColor color = backgroundColor();
  if (steering_angle != steering_angle_deg || color != background_color) {
    background_color = color;
    steering_angle_deg = steering_angle;
    update();
  }

  uint64_t current_wheel_image_update_count = (*fs.sm)["frogpilotPlan"].getFrogpilotPlan().getWheelImageUpdateCount();
  if (current_wheel_image_update_count != wheel_image_update_count) {
    wheel_image_update_count = current_wheel_image_update_count;
    updateTheme();
  }
}

QColor ExperimentalButton::backgroundColor() const {
  const UIScene &scene = uiState()->scene;
  const FrogPilotUIScene &frogpilot_scene = frogpilotUIState()->frogpilot_scene;

  if (!isDown() && engageable) {
    if (frogpilot_scene.always_on_lateral_active) {
      return bg_colors[STATUS_ALWAYS_ON_LATERAL_ACTIVE];
    } else if (frogpilot_scene.conditional_status == 1) {
      return bg_colors[STATUS_CEM_DISABLED];
    } else if (experimental_mode) {
      return bg_colors[STATUS_EXPERIMENTAL_MODE_ENABLED];
    } else if (scene.navigate_on_openpilot) {
      return bg_colors[STATUS_NAVIGATION_ACTIVE];
    } else if (frogpilot_scene.traffic_mode_enabled) {
      return bg_colors[STATUS_TRAFFIC_MODE_ENABLED];
    }
  }
  return QColor(0, 0, 0, 166);
}

void ExperimentalButton::paintEvent(QPaintEvent *event) {
  QPainter p(this);
  QPixmap img = experimental_mode ? experimental_img : engage_img;

  // FrogPilot variables
  if (!wheel_is_stock) {
    img = wheel_gif ? wheel_gif->currentPixmap() : wheel_img;
  }
  if (img.isNull()) {
    return;
  }

  p.setClipRegion(QRegion(QRect(0, 0, btn_size, btn_size), QRegion::Ellipse));
  p.translate(btn_size / 2, btn_size / 2);
  p.rotate(steering_angle_deg);
  p.translate(-btn_size / 2, -btn_size / 2);

  drawIcon(p, QPoint(btn_size / 2, btn_size / 2), img, backgroundColor(), (isDown() || !engageable) ? 0.6 : 1.0);
}

// MapSettingsButton
MapSettingsButton::MapSettingsButton(QWidget *parent) : QPushButton(parent) {
  setFixedSize(btn_size, btn_size + UI_BORDER_SIZE + 10);
  settings_img = loadPixmap("../assets/navigation/icon_directions_outlined.svg", {img_size, img_size});

  // hidden by default, made visible if map is created (has prime or mapbox token)
  setVisible(false);
  setEnabled(false);
}

void MapSettingsButton::paintEvent(QPaintEvent *event) {
  QPainter p(this);
  drawIcon(p, QPoint(btn_size / 2, btn_size / 2 + (road_name_ui ? 0 : UI_BORDER_SIZE + 10)), settings_img, QColor(0, 0, 0, 166), isDown() ? 0.6 : 1.0);
}
