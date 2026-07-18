import com.google.firebase.crashlytics.buildtools.gradle.CrashlyticsExtension
import com.google.gms.googleservices.GoogleServicesPlugin
import java.util.Properties

plugins {
    alias(libs.plugins.androidApplication)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.googleServices)
    alias(libs.plugins.firebaseCrashlytics)
}

kotlin {
    explicitApi()
    jvmToolchain(17)
}

android {
    lint {
        disable.add("NewerVersionAvailable")
    }

    signingConfigs {
        getByName("debug") {
            storeFile = file("../keys/zhixing-debug.jks")
            storePassword = "zhixing-debug"
            keyAlias = "zhixing-debug"
            keyPassword = "zhixing-debug"
        }
        //SHA1: 89:5F:34:AB:7B:EB:6B:A0:65:4E:56:CB:E4:8D:E3:22:25:29:22:FD
        //SHA256: 67:80:30:DE:17:FD:A4:B8:B2:1D:9F:D3:57:0D:5C:FB:2D:57:86:7C:46:51:70:06:22:3D:7D:1F:B0:7F:39:AC
    }

    // Source namespaces of the MIT transport kernel stay intact for upstream
    // maintenance; the installable product identity belongs to 知行智学.
    namespace = "info.dvkr.screenstream"
    compileSdk = rootProject.extra["compileSdkVersion"] as Int
    buildToolsVersion = rootProject.extra["buildToolsVersion"] as String
    ndkVersion = rootProject.extra["ndkVersion"] as String

    defaultConfig {
        applicationId = "cn.zhixingzhixue.mobile"
        minSdk = rootProject.extra["minSdkVersion"] as Int
        targetSdk = rootProject.extra["targetSdkVersion"] as Int
        versionCode = 10002
        versionName = "1.0.0-edge.1"

        ndk.abiFilters.addAll(listOf("armeabi-v7a", "x86", "arm64-v8a", "x86_64"))
    }

    androidResources {
        generateLocaleConfig = true
    }

    buildFeatures {
        buildConfig = true
        compose = true
    }

    buildTypes {
        debug {
            signingConfig = signingConfigs.getByName("debug")
            applicationIdSuffix = ".dev"
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
//            baselineProfile.automaticGenerationDuringBuild = true
        }
    }

    flavorDimensions += listOf("Default")
    productFlavors {
        create("FDroid") {
            dimension = "Default"
            manifestPlaceholders += mapOf("adMobPubId" to "")
            configure<CrashlyticsExtension> {
                mappingFileUploadEnabled = false
                nativeSymbolUploadEnabled = false
            }
        }
        create("PlayStore") {
            dimension = "Default"
            val localProps = Properties()
            File(rootProject.rootDir, "local.properties").apply { if (exists() && isFile) inputStream().use { localProps.load(it) } }
            manifestPlaceholders += mapOf("adMobPubId" to localProps.getProperty("ad.pubId", "\"\""))
            buildConfigField("String", "AD_UNIT_IDS", localProps.getProperty("ad.unitIds", "\"[]\""))
            configure<CrashlyticsExtension> {
                mappingFileUploadEnabled = true
                nativeSymbolUploadEnabled = true
            }
        }
    }

    compileOptions {
        isCoreLibraryDesugaringEnabled = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
            excludes += "custom.config.*"
            excludes += "DebugProbesKt.bin"
        }
    }
}

googleServices {
    // Play Store variants provide google-services.json; FDroid variants do not.
    missingGoogleServicesStrategy = GoogleServicesPlugin.MissingGoogleServicesStrategy.IGNORE
}

configurations.configureEach {
    exclude(group = "com.google.android.gms", module = "play-services-ads")
    exclude(group = "com.google.android.gms", module = "play-services-ads-lite")
}

tasks.configureEach {
    if (name.startsWith("processFDroid") && name.endsWith("GoogleServices")) {
        enabled = false
    }
    if (name.contains("FDroid") && name.startsWith("injectCrashlytics")) {
        enabled = false
    }
}

dependencies {
    coreLibraryDesugaring(libs.android.tools.desugar)

    implementation(projects.common)

    implementation(libs.androidx.core.splashscreen)
    implementation(libs.androidx.compose.material3.adaptive.navigation.suite)
    implementation(libs.androidx.compose.material3.adaptive.layout)
    implementation(libs.androidx.compose.material3.adaptive.navigation)

    implementation(projects.rtsp)
    implementation(projects.edgeAndroid)

    "PlayStoreImplementation"(projects.webrtc)
    "PlayStoreImplementation"(libs.play.app.update)
    "PlayStoreImplementation"(libs.play.app.review)
    "PlayStoreImplementation"(libs.ads.mobile.sdk)
    "PlayStoreImplementation"(libs.androidx.work.runtime) // Override the old transitive WorkManager from ads-mobile-sdk.
    "PlayStoreImplementation"(platform(libs.firebase.bom))
    "PlayStoreImplementation"(libs.firebase.analytics)
    "PlayStoreImplementation"(libs.firebase.crashlytics)
    "PlayStoreImplementation"(libs.firebase.crashlytics.ndk)
}
