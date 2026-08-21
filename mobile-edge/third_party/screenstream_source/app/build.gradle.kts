plugins {
    alias(libs.plugins.androidApplication)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

kotlin {
    explicitApi()
    jvmToolchain(17)
}

android {
    lint {
        disable.add("NewerVersionAvailable")
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
        versionCode = 10008
        versionName = "1.1.0-paired-pc-reliable-sync"

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
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
//            baselineProfile.automaticGenerationDuringBuild = true
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

dependencies {
    coreLibraryDesugaring(libs.android.tools.desugar)

    implementation(dependencies.project(":common"))

    implementation(libs.androidx.core.splashscreen)
    implementation(libs.androidx.compose.material3.adaptive.navigation.suite)
    implementation(libs.androidx.compose.material3.adaptive.layout)
    implementation(libs.androidx.compose.material3.adaptive.navigation)

    implementation(dependencies.project(":rtsp"))
    implementation(dependencies.project(":edge-android"))

}
