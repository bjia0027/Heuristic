#include "service_25.h"

Service25::Service25() {}

void Service25::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service25::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
