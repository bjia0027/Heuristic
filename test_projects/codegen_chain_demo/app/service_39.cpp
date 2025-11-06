#include "service_39.h"

Service39::Service39() {}

void Service39::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service39::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
