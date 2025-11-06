#include "service_9.h"

Service9::Service9() {}

void Service9::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service9::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
